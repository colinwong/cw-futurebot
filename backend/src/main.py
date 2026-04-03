import asyncio
import logging
import concurrent.futures
from contextlib import asynccontextmanager
from typing import Callable, TypeVar

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ib_insync import IB

from src.api.routes import market_data, orders, positions
from src.api.routes import settings as settings_routes
from src.api.routes import signals, strategy, trades, ws
from src.api.routes.ws import manager
from src.config import settings
from src.contracts import make_ib_contract
from src.db.models import SymbolEnum
from src.db.database import async_session
from src.db.models import ImpactRatingEnum, NewsEvent, SentimentEnum
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
_ib_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
_ib_loop: asyncio.AbstractEventLoop | None = None

T = TypeVar("T")


async def run_ib(fn: Callable[..., T], *args, **kwargs) -> T:
    """Run a synchronous ib_insync call in the dedicated IB thread."""
    def _run():
        global _ib_loop
        if _ib_loop is None:
            _ib_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_ib_loop)
        return fn(*args, **kwargs)

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ib_executor, _run)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ib
    logger.info("Starting cw-futurebot backend on port %d", settings.port)

    # Connect to IB Gateway in the dedicated IB thread
    ib = IB()
    try:
        await run_ib(
            ib.connect,
            host=settings.ib_host,
            port=settings.ib_port,
            clientId=settings.ib_client_id,
            readonly=False,
        )
        logger.info("Connected to IB Gateway at %s:%d", settings.ib_host, settings.ib_port)

        # Enable delayed data if no real-time subscription
        await run_ib(ib.reqMarketDataType, 4)  # 4 = delayed-frozen

        # Subscribe to market data for ES and NQ
        _streaming_task = asyncio.create_task(_start_market_data_streaming())
    except Exception as e:
        logger.warning("Could not connect to IB Gateway: %s", e)
        ib = None

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

# Track current candle per symbol for tick-based candle building
_current_candles: dict[str, dict] = {}
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

                    # Build/update the current candle
                    cur = _current_candles.get(sym)
                    if cur is None or cur["time"] != candle_time:
                        # Emit the previous candle if it exists
                        if cur is not None:
                            asyncio.run_coroutine_threadsafe(
                                manager.broadcast("candle", cur), main_loop
                            )
                        # Start new candle
                        _current_candles[sym] = {
                            "symbol": sym,
                            "time": candle_time,
                            "open": price,
                            "high": price,
                            "low": price,
                            "close": price,
                            "volume": int(t.volume) if t.volume == t.volume else 0,
                        }
                    else:
                        cur["high"] = max(cur["high"], price)
                        cur["low"] = min(cur["low"], price)
                        cur["close"] = price

                    # Always broadcast tick for live price display
                    tick_data = {
                        "symbol": sym,
                        "price": price,
                        "bid": t.bid if t.bid == t.bid else 0,
                        "ask": t.ask if t.ask == t.ask else 0,
                        "volume": int(t.volume) if t.volume == t.volume else 0,
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
app.include_router(orders.router)
app.include_router(signals.router)
app.include_router(market_data.router)
app.include_router(strategy.router)
app.include_router(settings_routes.router)
app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


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
    }
