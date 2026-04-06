import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Query

from src.config import EXCHANGE_TZ, UTC_TZ
from src.contracts import make_ib_contract
from src.db.models import SymbolEnum

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-data", tags=["market-data"])


def _ib_bar_to_utc_epoch(bar_date) -> int:
    """Convert IB bar date (naive ET) to UTC epoch seconds."""
    dt = bar_date if isinstance(bar_date, datetime) else datetime.fromisoformat(str(bar_date))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EXCHANGE_TZ)
    return int(dt.astimezone(UTC_TZ).timestamp())


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

    # Retry up to 2 times — IB can be flaky with 1-min data
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            await run_ib(ib.qualifyContracts, contract, timeout=5.0)
            bars = await run_ib(
                ib.reqHistoricalData,
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow="TRADES",
                useRTH=False,
                formatDate=2,
                timeout=20.0,
            )

            return {
                "symbol": symbol,
                "bar_size": bar_size,
                "candles": [
                    {
                        "time": _ib_bar_to_utc_epoch(bar.date),
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": int(bar.volume),
                    }
                    for bar in bars
                ],
            }
        except asyncio.TimeoutError:
            logger.warning(
                "IB historical data timeout for %s %s (attempt %d/%d)",
                symbol, bar_size, attempt + 1, max_retries + 1,
            )
            if attempt < max_retries:
                await asyncio.sleep(0.5)
                continue
            return {"candles": [], "error": f"IB data request timed out for {symbol} {bar_size}"}
        except Exception:
            logger.exception("Error fetching candles for %s %s", symbol, bar_size)
            return {"candles": [], "error": f"Failed to fetch {symbol} {bar_size} data"}
