"""Shared futures contract specifications. Single source of truth for ES/NQ metadata."""

from ib_insync import Contract

from src.db.models import SymbolEnum

FUTURES_CONTRACTS = {
    SymbolEnum.ES: {
        "exchange": "CME",
        "currency": "USD",
        "multiplier": 50,  # $50 per point
        "tick_size": 0.25,
    },
    SymbolEnum.NQ: {
        "exchange": "CME",
        "currency": "USD",
        "multiplier": 20,  # $20 per point
        "tick_size": 0.25,
    },
}


def make_ib_contract(symbol: SymbolEnum) -> Contract:
    """Create an IB futures contract for the given symbol."""
    spec = FUTURES_CONTRACTS[symbol]
    contract = Contract()
    contract.symbol = symbol.value
    contract.secType = "FUT"
    contract.exchange = spec["exchange"]
    contract.currency = spec["currency"]
    contract.lastTradeDateOrContractMonth = ""
    return contract
