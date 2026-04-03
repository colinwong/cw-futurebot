import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import EXCHANGE_TZ, UTC_TZ, settings
from src.db.models import (
    DirectionEnum,
    Position,
    SymbolEnum,
    TradeOutcome,
)
from src.strategy.base import StrategySignal

logger = logging.getLogger(__name__)


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
        result = await session.execute(
            select(func.sum(Position.quantity)).where(
                Position.symbol == symbol, Position.is_open.is_(True)
            )
        )
        current_size = result.scalar() or 0

        passed = current_size < settings.max_position_size
        return RiskCheckResult(
            name="max_position_size",
            passed=passed,
            threshold=settings.max_position_size,
            actual=current_size,
            message=f"Current {symbol.value} position size: {current_size}/{settings.max_position_size}"
            if passed
            else f"Max position size reached for {symbol.value}: {current_size}/{settings.max_position_size}",
        )

    async def _check_duplicate_position(
        self, symbol: SymbolEnum, direction: DirectionEnum, session: AsyncSession
    ) -> RiskCheckResult:
        result = await session.execute(
            select(Position).where(
                Position.symbol == symbol,
                Position.direction == direction,
                Position.is_open.is_(True),
            )
        )
        existing = result.scalars().first()

        passed = existing is None
        return RiskCheckResult(
            name="no_duplicate_position",
            passed=passed,
            threshold="no existing position in same direction",
            actual=f"existing {direction.value} position" if existing else "no duplicate",
            message=f"Already have an open {direction.value} position in {symbol.value}"
            if not passed
            else "No conflicting position",
        )

    async def _check_daily_loss(self, session: AsyncSession) -> RiskCheckResult:
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

        passed = daily_pnl > -settings.daily_loss_limit
        return RiskCheckResult(
            name="daily_loss_limit",
            passed=passed,
            threshold=f"-${settings.daily_loss_limit:.2f}",
            actual=f"${daily_pnl:.2f}",
            message=f"Daily P&L: ${daily_pnl:.2f} (limit: -${settings.daily_loss_limit:.2f})"
            if passed
            else f"Daily loss limit reached: ${daily_pnl:.2f} exceeds -${settings.daily_loss_limit:.2f}",
        )
