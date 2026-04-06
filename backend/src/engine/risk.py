import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.broker.base import BaseBroker
from src.config import EXCHANGE_TZ, UTC_TZ, settings
from src.contracts import FUTURES_CONTRACTS
from src.db.models import (
    AppSetting,
    DirectionEnum,
    Position,
    SymbolEnum,
    TradeOutcome,
)
from src.strategy.base import StrategySignal

logger = logging.getLogger(__name__)

# Approximate intraday margin per contract by symbol
_MARGIN_PER_CONTRACT = {
    SymbolEnum.MES: 1_500,
    SymbolEnum.MNQ: 1_500,
    SymbolEnum.ES: 15_000,
    SymbolEnum.NQ: 15_000,
}


@dataclass
class RiskCheckResult:
    """Result of a single risk check."""

    name: str
    passed: bool
    threshold: float | int | str
    actual: float | int | str
    message: str


@dataclass
class RiskEvaluation:
    """Full risk evaluation for a signal."""

    approved: bool
    checks: list[RiskCheckResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "threshold": c.threshold,
                    "actual": c.actual,
                    "message": c.message,
                }
                for c in self.checks
            ],
        }


class RiskManager:
    """Evaluates risk checks before allowing trade execution.

    Rules enforced:
    1. Max position size per symbol
    2. Daily loss limit
    3. No duplicate positions (already in a position for that symbol/direction)
    4. Bracket order required (stop + target must be provided)
    """

    def __init__(self, broker: BaseBroker | None = None):
        self._broker = broker

    async def _get_db_settings(self, session: AsyncSession) -> dict[str, str]:
        """Read all app settings from the database."""
        result = await session.execute(select(AppSetting))
        return {s.key: s.value for s in result.scalars().all()}

    async def _get_effective_max_position(
        self, symbol: SymbolEnum, session: AsyncSession
    ) -> int:
        """Get effective max position size based on risk mode (auto or manual)."""
        db_settings = await self._get_db_settings(session)
        risk_mode = db_settings.get("risk_mode", "manual")

        if risk_mode == "auto" and self._broker:
            try:
                account = await self._broker.get_account()
                margin_per = _MARGIN_PER_CONTRACT.get(symbol, 1_500)
                max_pct = float(db_settings.get("auto_max_position_pct", "40"))
                usable_margin = account.buying_power * (max_pct / 100)
                auto_max = max(1, int(usable_margin / margin_per))
                logger.info(
                    "Auto position sizing for %s: buying_power=%.0f, margin_per=%d, max_pct=%.1f%% → max=%d",
                    symbol.value, account.buying_power, margin_per, max_pct, auto_max,
                )
                return auto_max
            except Exception:
                logger.warning("Auto position sizing failed, falling back to manual")

        return int(db_settings.get("max_position_size", str(settings.max_position_size)))

    async def _get_effective_daily_loss_limit(self, session: AsyncSession) -> float:
        """Get effective daily loss limit based on risk mode."""
        db_settings = await self._get_db_settings(session)
        risk_mode = db_settings.get("risk_mode", "manual")

        if risk_mode == "auto" and self._broker:
            try:
                account = await self._broker.get_account()
                loss_pct = float(db_settings.get("auto_daily_loss_pct", "2.5"))
                auto_limit = round(account.balance * (loss_pct / 100), 2)
                return auto_limit
            except Exception:
                logger.warning("Auto daily loss calc failed, falling back to manual")

        return float(db_settings.get("daily_loss_limit", str(settings.daily_loss_limit)))

    async def calculate_position_size(
        self, symbol: SymbolEnum, session: AsyncSession
    ) -> int:
        """Calculate how many contracts to trade, respecting max position limits."""
        max_position = await self._get_effective_max_position(symbol, session)

        # Get current open position size for this symbol
        result = await session.execute(
            select(func.sum(Position.quantity)).where(
                Position.symbol == symbol, Position.is_open.is_(True)
            )
        )
        current_size = result.scalar() or 0

        # Available = max - current (at least 0)
        available = max(0, max_position - current_size)
        # For now, trade up to the available capacity (can refine with per-trade risk later)
        quantity = max(1, available) if available > 0 else 0

        logger.info(
            "Position sizing for %s: max=%d, current=%d, quantity=%d",
            symbol.value, max_position, current_size, quantity,
        )
        return quantity

    async def evaluate(
        self,
        signal: StrategySignal,
        stop_price: float | None,
        target_price: float | None,
        session: AsyncSession,
    ) -> RiskEvaluation:
        checks: list[RiskCheckResult] = []

        # Check 1: Bracket order required
        checks.append(self._check_bracket_order(stop_price, target_price))

        # Check 2: Max position size
        checks.append(await self._check_position_size(signal.symbol, session))

        # Check 3: No duplicate direction
        checks.append(await self._check_duplicate_position(signal.symbol, signal.direction, session))

        # Check 4: Daily loss limit
        checks.append(await self._check_daily_loss(session))

        all_passed = all(c.passed for c in checks)
        evaluation = RiskEvaluation(approved=all_passed, checks=checks)

        if not all_passed:
            failed = [c.name for c in checks if not c.passed]
            logger.info(
                "Risk evaluation REJECTED %s %s: failed checks = %s",
                signal.direction.value,
                signal.symbol.value,
                failed,
            )

        return evaluation

    def _check_bracket_order(
        self, stop_price: float | None, target_price: float | None
    ) -> RiskCheckResult:
        has_bracket = stop_price is not None and target_price is not None
        return RiskCheckResult(
            name="bracket_order_required",
            passed=has_bracket,
            threshold="stop + target required",
            actual=f"stop={stop_price}, target={target_price}",
            message="Bracket order (stop + target) is mandatory for every entry"
            if not has_bracket
            else "Bracket order provided",
        )

    async def _check_position_size(
        self, symbol: SymbolEnum, session: AsyncSession
    ) -> RiskCheckResult:
        max_position = await self._get_effective_max_position(symbol, session)

        result = await session.execute(
            select(func.sum(Position.quantity)).where(
                Position.symbol == symbol, Position.is_open.is_(True)
            )
        )
        current_size = result.scalar() or 0

        passed = current_size < max_position
        return RiskCheckResult(
            name="max_position_size",
            passed=passed,
            threshold=max_position,
            actual=current_size,
            message=f"Current {symbol.value} position size: {current_size}/{max_position}"
            if passed
            else f"Max position size reached for {symbol.value}: {current_size}/{max_position}",
        )

    async def _check_duplicate_position(
        self, symbol: SymbolEnum, direction: DirectionEnum, session: AsyncSession
    ) -> RiskCheckResult:
        # Block any open position on this symbol — no conflicting or duplicate positions
        result = await session.execute(
            select(Position).where(
                Position.symbol == symbol,
                Position.is_open.is_(True),
            )
        )
        existing = result.scalars().first()

        passed = existing is None
        if existing:
            if existing.direction == direction:
                msg = f"Already have an open {direction.value} position in {symbol.value}"
            else:
                msg = f"Conflicting {existing.direction.value} position already open in {symbol.value} — close it first"
        else:
            msg = "No existing position"

        return RiskCheckResult(
            name="no_conflicting_position",
            passed=passed,
            threshold="no existing open position on this symbol",
            actual=f"existing {existing.direction.value} position" if existing else "none",
            message=msg,
        )

    async def _check_daily_loss(self, session: AsyncSession) -> RiskCheckResult:
        daily_loss_limit = await self._get_effective_daily_loss_limit(session)

        # Reset at ET midnight (exchange timezone), convert to UTC for DB query
        today_start = (
            datetime.now(EXCHANGE_TZ)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(UTC_TZ)
        )

        result = await session.execute(
            select(func.sum(TradeOutcome.pnl)).where(
                TradeOutcome.id.in_(
                    select(TradeOutcome.id).join(Position).where(
                        Position.exit_timestamp >= today_start
                    )
                )
            )
        )
        daily_pnl = result.scalar() or 0.0

        passed = daily_pnl > -daily_loss_limit
        return RiskCheckResult(
            name="daily_loss_limit",
            passed=passed,
            threshold=f"-${daily_loss_limit:.2f}",
            actual=f"${daily_pnl:.2f}",
            message=f"Daily P&L: ${daily_pnl:.2f} (limit: -${daily_loss_limit:.2f})"
            if passed
            else f"Daily loss limit reached: ${daily_pnl:.2f} exceeds -${daily_loss_limit:.2f}",
        )
