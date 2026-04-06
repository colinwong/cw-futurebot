import asyncio
import logging
import concurrent.futures
from contextlib import asynccontextmanager
from typing import Callable, TypeVar

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ib_insync import IB

from src.api.routes import logs, market_data, orders, positions
from src.broker.ib_broker import IBBroker
from src.api.routes import settings as settings_routes
from src.api.routes import signals, strategy, trades, ws
from src.api.routes.ws import manager
from src.config import settings
from src.contracts import make_ib_contract
from src.db.models import SymbolEnum
from src.db.database import async_session
from src.db.models import (
    AppSetting,
    Decision,
    DecisionActionEnum,
    Fill,
    ImpactRatingEnum,
    MarketSnapshot,
    NewsEvent,
    Order as OrderModel,
    OrderStatusEnum,
    Position,
    SentimentEnum,
    Signal,
    SystemEvent,
    SystemEventTypeEnum,
)
from src.news.analyzer import NewsAnalyzer
from src.news.factory import create_news_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Shared IB connection — initialized in lifespan
ib: IB | None = None

# News provider + analyzer
_news_provider = None
_news_analyzer = None

# Dedicated thread pool for IB calls (ib_insync needs its own event loop)
_ib_executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
_thread_loops: dict[int, asyncio.AbstractEventLoop] = {}

T = TypeVar("T")


async def run_ib(fn: Callable[..., T], *args, **kwargs) -> T:
    """Run a synchronous ib_insync call in the IB thread pool."""
    def _run():
        import threading
        tid = threading.get_ident()
        if tid not in _thread_loops:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _thread_loops[tid] = loop
        return fn(*args, **kwargs)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ib_executor, _run)


_broker_ref: IBBroker | None = None
_engine_running = False


async def _connect_ib() -> bool:
    """Connect to IB Gateway and return True on success."""
    global ib
    try:
        ib = IB()
        await run_ib(
            ib.connect,
            host=settings.ib_host,
            port=settings.ib_port,
            clientId=settings.ib_client_id,
            readonly=False,
        )
        logger.info("Connected to IB Gateway at %s:%d", settings.ib_host, settings.ib_port)
        return True
    except Exception as e:
        logger.warning("Could not connect to IB Gateway: %s", e)
        ib = None
        return False


async def _post_connect_setup():
    """Set up everything that depends on a live IB connection.
    Called at startup and after every reconnect."""
    global _broker_ref

    # Enable delayed data if no real-time subscription
    await run_ib(ib.reqMarketDataType, 4)

    # Create/update broker for orders API
    if _broker_ref is None:
        _broker_ref = IBBroker(ib_instance=ib, executor=_ib_executor)
        orders.set_broker(_broker_ref)
    else:
        _broker_ref._ib = ib  # Swap to new IB instance
    logger.info("Broker wired to orders API")

    # Register fill tracking callback on this IB instance
    _setup_fill_tracking(asyncio.get_event_loop())

    # Start the algo strategy evaluation loop
    asyncio.create_task(_strategy_evaluation_loop())

    # Reconciliation
    await _startup_reconciliation()

    # Start market data streaming
    asyncio.create_task(_start_market_data_streaming())

    # Broadcast reconnect event to UI
    await manager.broadcast("system", {"event": "ib_connected"})


async def _reconnect_ib():
    """Reconnect to IB Gateway after a disconnect."""
    global ib
    # Disconnect old instance cleanly
    if ib is not None:
        try:
            await run_ib(ib.disconnect)
        except Exception:
            pass
        ib = None

    if await _connect_ib():
        await _post_connect_setup()
        return True
    return False


async def _ib_connection_monitor():
    """Check IB connection every 5 seconds. Auto-reconnect if disconnected."""
    await asyncio.sleep(10)  # Wait for initial startup to complete
    while True:
        await asyncio.sleep(5)
        try:
            if ib is None or not ib.isConnected():
                logger.warning("IB disconnected — attempting auto-reconnect...")
                success = await _reconnect_ib()
                if success:
                    logger.info("IB auto-reconnected successfully")
                else:
                    logger.warning("IB auto-reconnect failed — will retry in 5s")
        except Exception:
            logger.exception("Error in IB connection monitor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ib
    logger.info("Starting cw-futurebot backend on port %d", settings.port)

    # Initial IB connection
    if await _connect_ib():
        await _post_connect_setup()

    # Start connection monitor (auto-reconnect)
    asyncio.create_task(_ib_connection_monitor())

    # Start periodic reconciliation loop
    asyncio.create_task(_periodic_reconciliation_loop())

    # Start news provider + analyzer
    global _news_provider, _news_analyzer
    try:
        _news_provider = create_news_provider("finnhub")

        _news_analyzer = NewsAnalyzer()
        _news_analyzer.initialize()

        main_loop = asyncio.get_event_loop()

        def _on_news(item):
            async def _process_news():
                # Analyze with Claude if analyzer is available
                analysis = None
                if _news_analyzer:
                    analysis = await _news_analyzer.analyze(item)

                news_data = {
                    "id": item.id,
                    "timestamp": item.timestamp.isoformat(),
                    "source": item.source,
                    "url": item.url,
                    "headline": item.headline,
                    "relevance_score": analysis.get("relevance_score", 0) if analysis else 0,
                    "sentiment": analysis.get("sentiment", "NEUTRAL") if analysis else "NEUTRAL",
                    "impact_rating": analysis.get("impact_rating", "LOW") if analysis else "LOW",
                    "analysis": analysis,
                    "is_significant": analysis.get("impact_rating") in ("HIGH", "CRITICAL") if analysis else False,
                }
                # Persist to database
                try:
                    async with async_session() as session:
                        sentiment_val = analysis.get("sentiment", "NEUTRAL") if analysis else "NEUTRAL"
                        impact_val = analysis.get("impact_rating", "LOW") if analysis else "LOW"
                        news_event = NewsEvent(
                            timestamp=item.timestamp,
                            source=item.source,
                            headline=item.headline,
                            symbols=item.symbols or [],
                            raw_payload=item.raw_payload,
                            relevance_score=analysis.get("relevance_score", 0) if analysis else 0,
                            sentiment=SentimentEnum(sentiment_val),
                            impact_rating=ImpactRatingEnum(impact_val),
                            analysis=analysis,
                            is_significant=impact_val in ("HIGH", "CRITICAL"),
                        )
                        session.add(news_event)
                        await session.commit()
                except Exception:
                    logger.exception("Error persisting news event")

                await manager.broadcast("news", news_data, buffer=True)
                logger.info("News: [%s] %s", news_data["impact_rating"], item.headline[:60])

            asyncio.run_coroutine_threadsafe(_process_news(), main_loop)

        _news_provider.on_news(_on_news)
        await _news_provider.connect()
        logger.info("News provider (Finnhub) started")
    except Exception as e:
        logger.warning("Could not start news provider: %s", e)

    yield

    logger.info("Shutting down cw-futurebot backend")
    if _news_provider:
        await _news_provider.disconnect()
    if ib and ib.isConnected():
        await run_ib(ib.disconnect)
    _ib_executor.shutdown(wait=False)


import time as _time
from datetime import datetime as _datetime, timezone as _tz
from sqlalchemy import select as _select


async def _startup_reconciliation():
    """Compare DB state vs IB state on startup. Fix mismatches."""
    if not ib:
        return

    logger.info("Running startup reconciliation...")

    # Get IB positions
    ib_positions = await run_ib(ib.positions)
    ib_pos_map = {}
    for p in ib_positions:
        if p.position != 0 and p.contract.secType == "FUT":
            ib_pos_map[p.contract.symbol] = {
                "qty": int(p.position),
                "avg_price": p.avgCost / (50 if p.contract.symbol == "ES" else 20),  # IB avgCost includes multiplier
            }

    # Get IB open orders
    ib_orders = await run_ib(ib.openOrders)
    ib_order_ids = {o.orderId for o in ib_orders}

    async with async_session() as session:
        # Get DB open positions
        result = await session.execute(
            _select(Position).where(Position.is_open.is_(True))
        )
        db_positions = {pos.symbol.value: pos for pos in result.scalars().all()}

        discrepancies = []

        # Check: DB says open but IB has no position
        for symbol, db_pos in db_positions.items():
            if symbol not in ib_pos_map:
                discrepancies.append(f"DB has open {db_pos.direction.value} {symbol} but IB has no position — marking closed")
                db_pos.is_open = False
                db_pos.exit_timestamp = _datetime.now(_tz.utc)

        # Check: IB has position but DB doesn't — create a Position so UI can manage it
        for symbol, ib_info in ib_pos_map.items():
            if symbol not in db_positions:
                from src.db.models import DirectionEnum as _Dir, SymbolEnum as _Sym
                direction = "LONG" if ib_info["qty"] > 0 else "SHORT"
                new_pos = Position(
                    symbol=_Sym(symbol),
                    direction=_Dir(direction),
                    quantity=abs(ib_info["qty"]),
                    entry_price=ib_info["avg_price"],
                    entry_timestamp=_datetime.now(_tz.utc),
                    is_open=True,
                )
                session.add(new_pos)
                discrepancies.append(f"IB has {direction} {symbol} x{abs(ib_info['qty'])} @ {ib_info['avg_price']:.2f} — created Position in DB for management")

        # Check: DB has submitted orders that IB doesn't have
        from src.db.models import Order as OrderModel
        result = await session.execute(
            _select(OrderModel).where(OrderModel.status == OrderStatusEnum.SUBMITTED)
        )
        for order in result.scalars().all():
            if order.ib_order_id and order.ib_order_id not in ib_order_ids:
                discrepancies.append(f"DB order {order.ib_order_id} ({order.side.value} {order.symbol.value}) is SUBMITTED but not at IB — marking cancelled")
                order.status = OrderStatusEnum.CANCELLED

        await session.commit()

        if discrepancies:
            logger.warning("Reconciliation found %d discrepancies:", len(discrepancies))
            for d in discrepancies:
                logger.warning("  %s", d)

            # Log system event
            session.add(SystemEvent(
                event_type=SystemEventTypeEnum.RECONCILIATION,
                details={"discrepancies": discrepancies},
            ))
            await session.commit()
        else:
            logger.info("Reconciliation OK — DB and IB in sync")


async def _strategy_evaluation_loop():
    """Evaluate all strategies on a timer and generate signals."""
    from src.indicators import compute_indicators
    from src.strategy.vwap_trend import VWAPTrendContinuation
    from src.strategy.bollinger_reversion import BollingerMeanReversion
    from src.strategy.orb_momentum import ORBMomentum
    from src.engine.decision import DecisionEngine
    from src.engine.risk import RiskManager
    from src.contracts import make_ib_contract

    strategies = [VWAPTrendContinuation(), BollingerMeanReversion(), ORBMomentum()]
    risk_manager = RiskManager()
    decision_engine = DecisionEngine(_broker_ref, risk_manager) if _broker_ref else None

    await asyncio.sleep(5)  # Wait for market data to initialize
    logger.info("Strategy evaluation loop ready with %d strategies (waiting for engine start)", len(strategies))

    while True:
        await asyncio.sleep(settings.strategy_eval_interval)
        if not _engine_running:
            continue
        if not ib or not ib.isConnected():
            continue

        await manager.broadcast("system", {"event": "engine_eval_start", "interval": settings.strategy_eval_interval})

        for symbol in (SymbolEnum.ES, SymbolEnum.NQ):
            try:
                contract = make_ib_contract(symbol)
                try:
                    bars = await asyncio.wait_for(
                        run_ib(
                            ib.reqHistoricalData,
                            contract,
                            endDateTime="",
                            durationStr="2 D",
                            barSizeSetting="5 mins",
                            whatToShow="TRADES",
                            useRTH=False,
                            formatDate=2,
                        ),
                        timeout=15,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Historical data request timed out for %s", symbol.value)
                    continue

                if not bars or len(bars) < 50:
                    continue

                # Convert to dicts for indicator computation
                bar_dicts = [
                    {"open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": int(b.volume)}
                    for b in bars
                ]

                indicators = compute_indicators(bar_dicts)
                if not indicators:
                    continue

                last_bar = bars[-1]
                price = last_bar.close

                # Create market snapshot
                async with async_session() as session:
                    snapshot = MarketSnapshot(
                        symbol=symbol,
                        price=price,
                        bid=price,
                        ask=price,
                        volume=int(last_bar.volume),
                        indicators=indicators,
                        market_context={},
                    )
                    session.add(snapshot)
                    await session.flush()

                    # Evaluate each strategy
                    for strategy in strategies:
                        try:
                            signal = await strategy.evaluate(
                                symbol=symbol,
                                price=price,
                                bid=price,
                                ask=price,
                                volume=int(last_bar.volume),
                                indicators=indicators,
                                market_context={},
                                recent_news=[],
                            )

                            # Broadcast last eval result per strategy+symbol (pinned status)
                            await manager.broadcast("strategy_eval", {
                                "strategy": strategy.name,
                                "symbol": symbol.value,
                                "timestamp": _datetime.now(_tz.utc).isoformat(),
                                "price": price,
                                "has_signal": signal is not None,
                                "direction": signal.direction.value if signal else None,
                                "reasoning": signal.reasoning.get("description", "") if signal else "No conditions met",
                            })

                            if signal:
                                logger.info(
                                    "Signal: %s %s %s — %s",
                                    signal.strategy_name,
                                    signal.direction.value,
                                    symbol.value,
                                    signal.reasoning.get("description", "")[:80],
                                )

                                # Check trading mode
                                trading_mode = settings.trading_mode
                                from src.db.models import AppSetting
                                mode_result = await session.execute(
                                    _select(AppSetting).where(AppSetting.key == "trading_mode")
                                )
                                mode_setting = mode_result.scalars().first()
                                if mode_setting:
                                    trading_mode = mode_setting.value

                                # Always run risk check first
                                from src.engine.risk import RiskManager as _RM
                                _risk = _RM()
                                spec = FUTURES_CONTRACTS.get(signal.symbol, {})
                                tick_size = spec.get("tick_size", 0.25)
                                stop_ticks = signal.suggested_stop_ticks or int(settings.default_stop_ticks)
                                target_ticks = signal.suggested_target_ticks or int(settings.default_target_ticks)
                                if signal.direction.value == "LONG":
                                    stop_price = price - stop_ticks * tick_size
                                    target_price = price + target_ticks * tick_size
                                else:
                                    stop_price = price + stop_ticks * tick_size
                                    target_price = price - target_ticks * tick_size

                                risk_eval = await _risk.evaluate(signal, stop_price, target_price, session)

                                actual_action = "REJECT"
                                actual_reasoning = "Risk check failed"

                                if not risk_eval.approved:
                                    # Rejected by risk manager
                                    failed = [c for c in risk_eval.checks if not c.passed]
                                    actual_reasoning = "; ".join(f"{c.name}: {c.message}" for c in failed)
                                    actual_action = "REJECT"
                                elif trading_mode == "live" and decision_engine:
                                    await decision_engine.process_signal(signal, snapshot, session)
                                    actual_action = "EXECUTE"
                                    actual_reasoning = "Executed"
                                else:
                                    actual_action = "DEFER"
                                    actual_reasoning = "Signal-only mode"

                                # Persist signal + decision
                                sig_record = Signal(
                                    snapshot_id=snapshot.id,
                                    strategy_name=signal.strategy_name,
                                    symbol=signal.symbol,
                                    direction=signal.direction,
                                    strength=signal.strength,
                                    reasoning=signal.reasoning,
                                )
                                session.add(sig_record)
                                await session.flush()

                                dec_record = Decision(
                                    signal_id=sig_record.id,
                                    action=DecisionActionEnum(actual_action),
                                    risk_evaluation=risk_eval.to_dict(),
                                    decision_reasoning=actual_reasoning,
                                    stop_price=stop_price,
                                    target_price=target_price,
                                )
                                session.add(dec_record)

                                # Broadcast signal with ACTUAL decision to UI
                                await manager.broadcast("signal", {
                                    "id": f"live-{int(_time.time() * 1000)}",
                                    "timestamp": _datetime.now(_tz.utc).isoformat(),
                                    "strategy_name": signal.strategy_name,
                                    "symbol": symbol.value,
                                    "direction": signal.direction.value,
                                    "strength": signal.strength,
                                    "reasoning": signal.reasoning,
                                    "decision": {
                                        "action": actual_action,
                                        "reasoning": actual_reasoning,
                                    },
                                }, buffer=True)

                        except Exception:
                            logger.exception("Error evaluating strategy %s for %s", strategy.name, symbol.value)

                    await session.commit()

            except Exception:
                logger.exception("Error in strategy evaluation for %s", symbol.value)

        await manager.broadcast("system", {"event": "engine_eval_done"})


async def _periodic_reconciliation_loop():
    """Run reconciliation every reconciliation_interval seconds."""
    while True:
        await asyncio.sleep(settings.reconciliation_interval)
        try:
            await _startup_reconciliation()
        except Exception:
            logger.exception("Error in periodic reconciliation")


def _setup_fill_tracking(main_loop: asyncio.AbstractEventLoop):
    """Register IB callbacks to track order fills, update positions, and broadcast events."""
    if not ib:
        return

    from src.db.models import DirectionEnum as _Dir, TradeOutcome
    from src.contracts import FUTURES_CONTRACTS

    def _on_order_status(trade):
        ib_order_id = trade.order.orderId
        status = trade.orderStatus.status

        if status == "Filled":
            fill_price = trade.orderStatus.avgFillPrice
            filled_qty = int(trade.orderStatus.filled)

            async def _process_fill():
                try:
                    async with async_session() as session:
                        result = await session.execute(
                            _select(OrderModel).where(OrderModel.ib_order_id == ib_order_id)
                        )
                        order = result.scalars().first()
                        if not order:
                            logger.warning("Fill for unknown ib_order_id %d — skipping", ib_order_id)
                            return

                        # Update order status
                        order.status = OrderStatusEnum.FILLED
                        order.filled_at = _datetime.now(_tz.utc)

                        # Create Fill record
                        fill = Fill(
                            order_id=order.id,
                            fill_price=fill_price,
                            quantity=filled_qty,
                            commission=0.0,
                            slippage=0.0,
                            ib_execution_id=str(ib_order_id),
                        )
                        session.add(fill)

                        # Determine if this is an ENTRY fill or EXIT fill
                        # Entry: position with entry_price=0 and matching symbol (unfilled entry)
                        # Exit: position that is open, and this order is the opposite side
                        pos_updated = False

                        # Check for entry fill (position with no entry price yet)
                        entry_pos_result = await session.execute(
                            _select(Position).where(
                                Position.symbol == order.symbol,
                                Position.is_open.is_(True),
                                Position.entry_price == 0,
                            )
                        )
                        entry_pos = entry_pos_result.scalars().first()
                        if entry_pos:
                            entry_pos.entry_price = fill_price
                            entry_pos.entry_timestamp = _datetime.now(_tz.utc)
                            logger.info("Entry fill: Position %d %s @ %.2f", entry_pos.id, entry_pos.symbol.value, fill_price)
                            pos_updated = True

                        # Check for exit fill (close order for an open position)
                        if not pos_updated:
                            # Exit fill: find open position where this order closes it
                            # (opposite side — BUY closes SHORT, SELL closes LONG)
                            if order.side.value == "BUY":
                                exit_dir = _Dir.SHORT
                            else:
                                exit_dir = _Dir.LONG

                            exit_pos_result = await session.execute(
                                _select(Position).where(
                                    Position.symbol == order.symbol,
                                    Position.direction == exit_dir,
                                    Position.is_open.is_(True),
                                )
                            )
                            exit_pos = exit_pos_result.scalars().first()
                            if exit_pos:
                                exit_pos.is_open = False
                                exit_pos.exit_price = fill_price
                                exit_pos.exit_timestamp = _datetime.now(_tz.utc)

                                # Calculate P&L
                                if exit_pos.entry_price > 0:
                                    spec = FUTURES_CONTRACTS.get(exit_pos.symbol)
                                    multiplier = spec["multiplier"] if spec else 50
                                    if exit_pos.direction == _Dir.LONG:
                                        pnl = (fill_price - exit_pos.entry_price) * multiplier * exit_pos.quantity
                                    else:
                                        pnl = (exit_pos.entry_price - fill_price) * multiplier * exit_pos.quantity

                                    hold_secs = int((exit_pos.exit_timestamp - exit_pos.entry_timestamp).total_seconds())
                                    outcome = TradeOutcome(
                                        position_id=exit_pos.id,
                                        pnl=pnl,
                                        hold_duration_seconds=hold_secs,
                                    )
                                    session.add(outcome)
                                    logger.info("Exit fill: Position %d closed @ %.2f, P&L=$%.2f", exit_pos.id, fill_price, pnl)
                                else:
                                    logger.info("Exit fill: Position %d closed @ %.2f (no entry price, P&L unknown)", exit_pos.id, fill_price)
                                pos_updated = True

                        await session.commit()
                        logger.info("Fill recorded: ib_order=%d, price=%.2f, qty=%d", ib_order_id, fill_price, filled_qty)

                        # Broadcast ALL relevant events to UI
                        await manager.broadcast("order", {
                            "action": "filled",
                            "ib_order_id": ib_order_id,
                            "symbol": order.symbol.value,
                            "side": order.side.value,
                            "fill_price": fill_price,
                            "quantity": filled_qty,
                        })
                        await manager.broadcast("position", {"action": "updated"})

                        # Broadcast account update so P&L reflects immediately
                        try:
                            summary = await run_ib(ib.accountSummary)
                            values = {}
                            for item in summary:
                                values[item.tag] = item.value
                            await manager.broadcast("account", {
                                "balance": float(values.get("NetLiquidation", 0)),
                                "unrealized_pnl": float(values.get("UnrealizedPnL", 0)),
                                "realized_pnl": float(values.get("RealizedPnL", 0)),
                                "margin_used": float(values.get("InitMarginReq", 0)),
                                "buying_power": float(values.get("BuyingPower", 0)),
                            })
                        except Exception:
                            pass  # Account update is best-effort

                except Exception:
                    logger.exception("Error processing fill for ib_order=%d", ib_order_id)

            asyncio.run_coroutine_threadsafe(_process_fill(), main_loop)

    def _register():
        ib.orderStatusEvent += _on_order_status

    asyncio.get_event_loop().run_in_executor(_ib_executor, _register)
    logger.info("Fill tracking registered")


# Track current candle per symbol for tick-based candle building
_current_candles: dict[str, dict] = {}
_prev_volume: dict[str, int] = {}  # Track previous cumulative volume per symbol for delta computation
_CANDLE_INTERVAL = 5  # seconds — build 5-second candles from ticks


async def _start_market_data_streaming():
    """Subscribe to IB tick data for ES/NQ, build candles, and broadcast via WebSocket."""
    if not ib:
        return

    main_loop = asyncio.get_event_loop()

    for symbol in (SymbolEnum.ES, SymbolEnum.NQ):
        contract = make_ib_contract(symbol)
        await run_ib(ib.qualifyContracts, contract)

        # Request streaming tick data (works with delayed data too)
        def _subscribe_ticks(c=contract, s=symbol):
            ib.reqMktData(c, "", False, False)
            ticker = ib.ticker(c)
            if ticker:
                def _on_tick(t):
                    price = t.last if t.last == t.last else (t.close if t.close == t.close else 0)
                    if price == 0 or price != price:
                        return

                    now = _time.time()
                    candle_time = int(now // _CANDLE_INTERVAL) * _CANDLE_INTERVAL
                    sym = s.value

                    # Compute volume delta (IB sends cumulative session volume)
                    raw_vol = int(t.volume) if t.volume == t.volume else 0
                    prev_vol = _prev_volume.get(sym, 0)
                    vol_delta = max(0, raw_vol - prev_vol) if prev_vol > 0 else 0
                    _prev_volume[sym] = raw_vol

                    # Build/update the current candle
                    cur = _current_candles.get(sym)
                    if cur is None or cur["time"] != candle_time:
                        if cur is not None:
                            asyncio.run_coroutine_threadsafe(
                                manager.broadcast("candle", cur), main_loop
                            )
                        _current_candles[sym] = {
                            "symbol": sym,
                            "time": candle_time,
                            "open": price,
                            "high": price,
                            "low": price,
                            "close": price,
                            "volume": vol_delta,
                        }
                    else:
                        cur["high"] = max(cur["high"], price)
                        cur["low"] = min(cur["low"], price)
                        cur["close"] = price
                        cur["volume"] += vol_delta

                    # Always broadcast tick for live price display
                    tick_data = {
                        "symbol": sym,
                        "price": price,
                        "bid": t.bid if t.bid == t.bid else 0,
                        "ask": t.ask if t.ask == t.ask else 0,
                        "volume": vol_delta,
                        "timestamp": int(now),
                    }
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast("tick", tick_data), main_loop
                    )

                ticker.updateEvent += _on_tick

        await run_ib(_subscribe_ticks)
        logger.info("Subscribed to tick data for %s", symbol.value)

    # Keep IB event loop running to process callbacks + flush candles periodically
    async def _ib_sleep_loop():
        while ib and ib.isConnected():
            await run_ib(ib.sleep, 0.1)

            # Flush any stale candles (older than interval)
            now = _time.time()
            candle_time = int(now // _CANDLE_INTERVAL) * _CANDLE_INTERVAL
            for sym, cur in list(_current_candles.items()):
                if cur["time"] < candle_time:
                    await manager.broadcast("candle", cur)
                    del _current_candles[sym]

            await asyncio.sleep(0.05)

    asyncio.create_task(_ib_sleep_loop())


app = FastAPI(
    title="cw-futurebot",
    description="Futures trading algo bot for ES and NQ",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register routes
app.include_router(trades.router)
app.include_router(positions.router)
app.include_router(logs.router)
app.include_router(orders.router)
app.include_router(signals.router)
app.include_router(market_data.router)
app.include_router(strategy.router)
app.include_router(settings_routes.router)
app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/system/reconnect-ib")
async def reconnect_ib():
    """Manually trigger IB Gateway reconnection."""
    try:
        success = await _reconnect_ib()
        if success:
            return {"status": "connected", "message": "IB Gateway reconnected successfully"}
        else:
            return {"status": "failed", "message": "Could not connect to IB Gateway"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/system/engine/start")
async def start_engine():
    """Start the algo trading engine."""
    global _engine_running
    _engine_running = True
    logger.info("Algo engine STARTED")
    await manager.broadcast("system", {"event": "engine_started"})
    return {"status": "running"}


@app.post("/api/system/engine/stop")
async def stop_engine():
    """Stop the algo trading engine."""
    global _engine_running
    _engine_running = False
    logger.info("Algo engine STOPPED")
    await manager.broadcast("system", {"event": "engine_stopped"})
    return {"status": "stopped"}


@app.get("/api/system/engine/status")
async def engine_status():
    """Get the algo engine status."""
    return {"running": _engine_running}


@app.get("/api/status")
async def status():
    ib_connected = ib is not None and ib.isConnected()
    account_info = None

    if ib_connected:
        try:
            summary = await run_ib(ib.accountSummary)
            values = {}
            for item in summary:
                values[item.tag] = item.value
            account_info = {
                "balance": float(values.get("NetLiquidation", 0)),
                "unrealized_pnl": float(values.get("UnrealizedPnL", 0)),
                "realized_pnl": float(values.get("RealizedPnL", 0)),
                "margin_used": float(values.get("InitMarginReq", 0)),
                "buying_power": float(values.get("BuyingPower", 0)),
            }
        except Exception:
            logger.exception("Error fetching account summary")

    ib_account = settings.ib_account or None
    if ib_connected and not ib_account:
        try:
            accounts = await run_ib(ib.managedAccounts)
            ib_account = accounts[0] if accounts else None
        except Exception:
            pass

    return {
        "ib_connected": ib_connected,
        "ib_account": ib_account,
        "account": account_info,
        "engine_running": _engine_running,
    }
