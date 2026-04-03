import asyncio
import logging
import concurrent.futures
from contextlib import asynccontextmanager
from typing import Callable, TypeVar

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ib_insync import IB

from src.api.routes import market_data, orders, positions, signals, strategy, trades, ws
from src.api.routes.ws import manager
from src.config import settings
from src.contracts import make_ib_contract
from src.db.models import SymbolEnum

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Shared IB connection — initialized in lifespan
ib: IB | None = None

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

    yield

    logger.info("Shutting down cw-futurebot backend")
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
