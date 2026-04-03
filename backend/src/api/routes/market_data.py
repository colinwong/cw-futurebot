from datetime import datetime

from fastapi import APIRouter, Query

from src.contracts import make_ib_contract
from src.db.models import SymbolEnum

router = APIRouter(prefix="/api/market-data", tags=["market-data"])


@router.get("/{symbol}/candles")
async def get_candles(
    symbol: str,
    bar_size: str = Query("5 mins", description="Bar size: '1 min', '5 mins', '15 mins', '1 hour'"),
    duration: str = Query("1 D", description="Duration: '1 D', '2 D', '1 W'"),
):
    """Get historical candles for chart initialization."""
    from src.main import ib, run_ib

    if not ib or not ib.isConnected():
        return {"candles": [], "error": "IB not connected"}

    sym = SymbolEnum(symbol)
    contract = make_ib_contract(sym)

    await run_ib(ib.qualifyContracts, contract)
    bars = await run_ib(
        ib.reqHistoricalData,
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow="TRADES",
        useRTH=False,
        formatDate=2,
    )

    return {
        "symbol": symbol,
        "bar_size": bar_size,
        "candles": [
            {
                "time": int(bar.date.timestamp()) if isinstance(bar.date, datetime) else int(datetime.fromisoformat(str(bar.date)).timestamp()),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": int(bar.volume),
            }
            for bar in bars
        ],
    }
