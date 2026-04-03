from fastapi import APIRouter, Depends, Query

from src.db.models import SymbolEnum

router = APIRouter(prefix="/api/market-data", tags=["market-data"])

# Market data instance will be set during app startup
_market_data = None


def set_market_data(market_data):
    global _market_data
    _market_data = market_data


@router.get("/{symbol}/candles")
async def get_candles(
    symbol: str,
    bar_size: str = Query("5 mins", description="Bar size: '1 min', '5 mins', '15 mins', '1 hour'"),
    duration: str = Query("1 D", description="Duration: '1 D', '2 D', '1 W'"),
):
    """Get historical candles for chart initialization."""
    if not _market_data:
        return {"candles": [], "error": "Market data not connected"}

    sym = SymbolEnum(symbol)
    bars = await _market_data.get_historical_bars(sym, bar_size, duration)

    return {
        "symbol": symbol,
        "bar_size": bar_size,
        "candles": [
            {
                "time": int(bar.timestamp.timestamp()),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ],
    }
