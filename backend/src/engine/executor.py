import asyncio
import logging
import signal
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.broker.base import BaseBroker
from src.config import settings
from src.data.base import BaseMarketData, Tick
from src.db.database import async_session
from src.db.models import (
    MarketSnapshot,
    StrategyLog,
    SystemEvent,
    SystemEventTypeEnum,
    SymbolEnum,
)
from src.engine.decision import DecisionEngine
from src.engine.reconciliation import Reconciler
from src.engine.risk import RiskManager
from src.strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


class TradingExecutor:
    """Hybrid execution engine.

    - Polling loop: evaluates strategies at fixed intervals
    - Event-driven: handles order fills and position updates via broker callbacks
    - Periodic: runs reconciliation checks
    - Monitors connection health and sends Telegram alerts
    """

    def __init__(
        self,
        broker: BaseBroker,
        market_data: BaseMarketData,
        strategies: list[BaseStrategy],
        telegram_notify: callable | None = None,
    ):
        self._broker = broker
        self._market_data = market_data
        self._strategies = strategies
        self._telegram_notify = telegram_notify

        self._risk_manager = RiskManager()
        self._decision_engine = DecisionEngine(broker, self._risk_manager)
        self._reconciler = Reconciler(broker)

        self._running = False
        self._latest_ticks: dict[SymbolEnum, Tick] = {}

    async def start(self) -> None:
        """Start the trading engine."""
        self._running = True

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        # Log startup
        async with async_session() as session:
            session.add(SystemEvent(
                event_type=SystemEventTypeEnum.STARTUP,
                details={"strategies": [s.name for s in self._strategies]},
            ))
            await session.commit()

        # Run startup reconciliation
        await self._run_reconciliation()

        # Subscribe to market data
        self._market_data.on_tick(self._handle_tick)
        for symbol in (SymbolEnum.MES, SymbolEnum.MNQ):
            await self._market_data.subscribe(symbol)

        # Register broker callbacks
        self._broker.on_execution(self._handle_execution)
        self._broker.on_connection_status(self._handle_connection_change)

        # Start async tasks
        await asyncio.gather(
            self._strategy_loop(),
            self._reconciliation_loop(),
        )

    async def stop(self) -> None:
        """Graceful shutdown."""
        if not self._running:
            return

        logger.info("Initiating graceful shutdown...")
        self._running = False

        # Log shutdown event
        async with async_session() as session:
            session.add(SystemEvent(
                event_type=SystemEventTypeEnum.SHUTDOWN,
                details={"reason": "signal received"},
            ))
            await session.commit()

        # Verify protective orders are in place (do NOT close positions)
        await self._run_reconciliation()

        await self._market_data.disconnect()
        logger.info("Trading executor stopped")

    async def _strategy_loop(self) -> None:
        """Main polling loop: evaluate strategies at fixed intervals."""
        while self._running:
            try:
                await self._evaluate_all_strategies()
            except Exception:
                logger.exception("Error in strategy evaluation loop")

            await asyncio.sleep(settings.strategy_eval_interval)

    async def _reconciliation_loop(self) -> None:
        """Periodic reconciliation loop."""
        while self._running:
            await asyncio.sleep(settings.reconciliation_interval)
            try:
                await self._run_reconciliation()
            except Exception:
                logger.exception("Error in reconciliation loop")

    async def _evaluate_all_strategies(self) -> None:
        """Evaluate all strategies for all symbols."""
        for symbol in (SymbolEnum.MES, SymbolEnum.MNQ):
            tick = self._latest_ticks.get(symbol)
            if not tick:
                continue

            async with async_session() as session:
                # Capture market snapshot
                snapshot = MarketSnapshot(
                    symbol=symbol,
                    price=tick.price,
                    bid=tick.bid,
                    ask=tick.ask,
                    volume=tick.volume,
                    indicators={},  # TODO: compute indicators
                    market_context={},  # TODO: session info
                )
                session.add(snapshot)
                await session.flush()

                # Evaluate each strategy
                for strategy in self._strategies:
                    try:
                        signal = await strategy.evaluate(
                            symbol=symbol,
                            price=tick.price,
                            bid=tick.bid,
                            ask=tick.ask,
                            volume=tick.volume,
                            indicators=snapshot.indicators,
                            market_context=snapshot.market_context,
                            recent_news=[],  # TODO: pass recent news
                        )

                        # Log strategy state
                        state = await strategy.get_state(symbol)
                        session.add(StrategyLog(
                            strategy_name=strategy.name,
                            symbol=symbol,
                            state={
                                "indicator_values": state.indicator_values,
                                "conditions_met": state.conditions_met,
                                "notes": state.notes,
                            },
                        ))

                        # Process signal through decision engine
                        if signal:
                            await self._decision_engine.process_signal(signal, snapshot, session)

                    except Exception:
                        logger.exception(
                            "Error evaluating strategy %s for %s", strategy.name, symbol.value
                        )

                await session.commit()

    async def _run_reconciliation(self) -> None:
        """Run reconciliation and notify if discrepancies found."""
        async with async_session() as session:
            result = await self._reconciler.reconcile(session)

            if result.has_discrepancies and self._telegram_notify:
                await self._telegram_notify(
                    f"Reconciliation discrepancies found:\n{result.to_dict()}"
                )

    def _handle_tick(self, tick: Tick) -> None:
        """Store latest tick for each symbol."""
        self._latest_ticks[tick.symbol] = tick

    def _handle_execution(self, trade, fill) -> None:
        """Handle order execution/fill events from broker."""
        logger.info(
            "Execution: order=%d, price=%.2f, qty=%d",
            trade.order.orderId,
            fill.execution.price,
            fill.execution.shares,
        )
        # TODO: Update order status and fill records in DB

    def _handle_connection_change(self, connected: bool) -> None:
        """Handle broker connection status changes."""
        if connected:
            logger.info("Broker reconnected — running reconciliation")
            asyncio.create_task(self._run_reconciliation())
            asyncio.create_task(self._log_system_event(SystemEventTypeEnum.RECONNECT, {}))
        else:
            logger.warning("Broker disconnected!")
            asyncio.create_task(
                self._log_system_event(SystemEventTypeEnum.DISCONNECT, {})
            )
            if self._telegram_notify:
                asyncio.create_task(
                    self._telegram_notify("ALERT: Broker connection lost!")
                )

    async def _log_system_event(
        self, event_type: SystemEventTypeEnum, details: dict
    ) -> None:
        async with async_session() as session:
            session.add(SystemEvent(event_type=event_type, details=details))
            await session.commit()
