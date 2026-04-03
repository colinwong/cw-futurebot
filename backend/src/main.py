import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import market_data, orders, positions, signals, strategy, trades, ws
from src.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting cw-futurebot backend on port %d", settings.port)
    # TODO: Initialize database, broker connection, engine, telegram bot
    yield
    logger.info("Shutting down cw-futurebot backend")
    # TODO: Graceful shutdown — verify protective orders, cancel pending orders, log event


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
