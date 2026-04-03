import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.broker.base import BaseBroker
from src.config import settings
from src.contracts import FUTURES_CONTRACTS
from src.db.models import (
    Decision,
    DecisionActionEnum,
    DirectionEnum,
    MarketSnapshot,
    Order,
    OrderSideEnum,
    OrderStatusEnum,
    OrderTypeEnum,
    Position,
    ProtectiveOrder,
    Signal,
    SymbolEnum,
)
from src.engine.risk import RiskManager
from src.strategy.base import StrategySignal

logger = logging.getLogger(__name__)


class DecisionEngine:
    """Core audit bridge: receives signals, evaluates risk, executes orders, persists everything."""

    def __init__(self, broker: BaseBroker, risk_manager: RiskManager):
        self._broker = broker
        self._risk_manager = risk_manager

    async def process_signal(
        self,
        strategy_signal: StrategySignal,
        snapshot: MarketSnapshot,
        session: AsyncSession,
    ) -> Decision:
        """Process a strategy signal through the full decision pipeline.

        1. Persist the signal
        2. Calculate stop/target prices
        3. Run risk evaluation
        4. If approved, place bracket order at broker
        5. Persist the decision with full context
        """
        # Step 1: Persist the signal
        signal = Signal(
            snapshot_id=snapshot.id,
            strategy_name=strategy_signal.strategy_name,
            symbol=strategy_signal.symbol,
            direction=strategy_signal.direction,
            strength=strategy_signal.strength,
            reasoning=strategy_signal.reasoning,
        )
        session.add(signal)
        await session.flush()

        # Step 2: Calculate stop/target prices
        spec = FUTURES_CONTRACTS[strategy_signal.symbol]
        tick_size = spec["tick_size"]
        stop_ticks = strategy_signal.suggested_stop_ticks or settings.default_stop_ticks
        target_ticks = strategy_signal.suggested_target_ticks or settings.default_target_ticks

        if strategy_signal.direction == DirectionEnum.LONG:
            stop_price = snapshot.price - (stop_ticks * tick_size)
            target_price = snapshot.price + (target_ticks * tick_size)
        else:
            stop_price = snapshot.price + (stop_ticks * tick_size)
            target_price = snapshot.price - (target_ticks * tick_size)

        # Step 3: Run risk evaluation
        risk_eval = await self._risk_manager.evaluate(
            strategy_signal, stop_price, target_price, session
        )

        # Step 4: Create decision
        if risk_eval.approved:
            decision = await self._execute_trade(
                signal, strategy_signal, snapshot, stop_price, target_price, risk_eval, session
            )
        else:
            decision = Decision(
                signal_id=signal.id,
                action=DecisionActionEnum.REJECT,
                risk_evaluation=risk_eval.to_dict(),
                decision_reasoning=self._build_rejection_reasoning(risk_eval),
                stop_price=stop_price,
                target_price=target_price,
            )
            session.add(decision)

        await session.commit()
        logger.info(
            "Decision: %s %s %s — %s",
            decision.action.value,
            strategy_signal.direction.value,
            strategy_signal.symbol.value,
            decision.decision_reasoning[:100],
        )
        return decision

    async def _execute_trade(
        self,
        signal: Signal,
        strategy_signal: StrategySignal,
        snapshot: MarketSnapshot,
        stop_price: float,
        target_price: float,
        risk_eval: RiskEvaluation,
        session: AsyncSession,
    ) -> Decision:
        """Place bracket order and persist all related records."""
        decision = Decision(
            signal_id=signal.id,
            action=DecisionActionEnum.EXECUTE,
            risk_evaluation=risk_eval.to_dict(),
            decision_reasoning=self._build_execution_reasoning(strategy_signal, stop_price, target_price),
            stop_price=stop_price,
            target_price=target_price,
        )
        session.add(decision)
        await session.flush()

        # Place bracket order at broker
        bracket_result = await self._broker.place_bracket_order(
            symbol=strategy_signal.symbol,
            direction=strategy_signal.direction,
            quantity=1,  # TODO: position sizing logic
            entry_order_type="MARKET",
            entry_price=None,
            stop_price=stop_price,
            target_price=target_price,
        )

        # Persist the entry order
        side = OrderSideEnum.BUY if strategy_signal.direction == DirectionEnum.LONG else OrderSideEnum.SELL
        entry_order = Order(
            decision_id=decision.id,
            symbol=strategy_signal.symbol,
            side=side,
            order_type=OrderTypeEnum.MARKET,
            quantity=1,
            ib_order_id=bracket_result.entry_order_id,
            status=OrderStatusEnum.SUBMITTED,
        )
        session.add(entry_order)

        # Persist the stop order
        stop_side = OrderSideEnum.SELL if strategy_signal.direction == DirectionEnum.LONG else OrderSideEnum.BUY
        stop_order = Order(
            decision_id=decision.id,
            symbol=strategy_signal.symbol,
            side=stop_side,
            order_type=OrderTypeEnum.STOP,
            quantity=1,
            stop_price=stop_price,
            ib_order_id=bracket_result.stop_order_id,
            status=OrderStatusEnum.SUBMITTED,
        )
        session.add(stop_order)

        # Persist the target order
        target_order = Order(
            decision_id=decision.id,
            symbol=strategy_signal.symbol,
            side=stop_side,
            order_type=OrderTypeEnum.LIMIT,
            quantity=1,
            limit_price=target_price,
            ib_order_id=bracket_result.target_order_id,
            status=OrderStatusEnum.SUBMITTED,
        )
        session.add(target_order)
        await session.flush()

        # Create position record
        position = Position(
            symbol=strategy_signal.symbol,
            direction=strategy_signal.direction,
            quantity=1,
            entry_price=snapshot.price,
            entry_timestamp=datetime.now(timezone.utc),
            entry_decision_id=decision.id,
            is_open=True,
        )
        session.add(position)
        await session.flush()

        # Track protective orders
        protective = ProtectiveOrder(
            position_id=position.id,
            stop_order_id=stop_order.id,
            target_order_id=target_order.id,
            stop_ib_order_id=bracket_result.stop_order_id,
            target_ib_order_id=bracket_result.target_order_id,
            verified_at=datetime.now(timezone.utc),
        )
        session.add(protective)

        return decision

    def _build_execution_reasoning(
        self, signal: StrategySignal, stop_price: float, target_price: float
    ) -> str:
        risk_desc = signal.reasoning.get("description", "")
        return (
            f"Executing {signal.direction.value} {signal.symbol.value}: {risk_desc}. "
            f"Stop at {stop_price:.2f}, target at {target_price:.2f}. "
            f"Signal strength: {signal.strength:.2f}."
        )

    def _build_rejection_reasoning(self, risk_eval: RiskEvaluation) -> str:
        failed = [c for c in risk_eval.checks if not c.passed]
        reasons = "; ".join(f"{c.name}: {c.message}" for c in failed)
        return f"Rejected — {reasons}"
