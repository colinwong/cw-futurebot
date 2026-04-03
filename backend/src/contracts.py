"""Shared futures contract specifications. Single source of truth for ES/NQ metadata."""

from datetime import datetime

from ib_insync import Contract

from src.config import EXCHANGE_TZ
from src.db.models import SymbolEnum

FUTURES_CONTRACTS = {
    SymbolEnum.ES: {
        "exchange": "CME",
        "currency": "USD",
        "multiplier": 50,  # $50 per point
        "tick_size": 0.25,
        "trading_class": "ES",
    },
    SymbolEnum.NQ: {
        "exchange": "CME",
        "currency": "USD",
        "multiplier": 20,  # $20 per point
        "tick_size": 0.25,
        "trading_class": "NQ",
    },
}

# ES/NQ expiry months: March (H), June (M), September (U), December (Z)
_QUARTER_MONTHS = [(3, "H"), (6, "M"), (9, "U"), (12, "Z")]


def _front_month_expiry() -> str:
    """Get the front-month contract expiry in YYYYMM format."""
    now = datetime.now(EXCHANGE_TZ)
    for month, _code in _QUARTER_MONTHS:
        # Contract expires 3rd Friday of the month; use month as cutoff
        if now.month <= month:
            return f"{now.year}{month:02d}"
    # Past December — next year March
    return f"{now.year + 1}03"


def make_ib_contract(symbol: SymbolEnum) -> Contract:
    """Create an IB futures contract for the front-month of the given symbol."""
    spec = FUTURES_CONTRACTS[symbol]
    contract = Contract()
    contract.symbol = symbol.value
    contract.secType = "FUT"
    contract.exchange = spec["exchange"]
    contract.currency = spec["currency"]
    contract.lastTradeDateOrContractMonth = _front_month_expiry()
    contract.tradingClass = spec["trading_class"]
    return contract
