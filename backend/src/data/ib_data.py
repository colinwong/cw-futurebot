import logging
from datetime import datetime, timezone
from typing import Callable

from ib_insync import IB

from src.contracts import make_ib_contract
from src.data.base import Bar, BaseMarketData, Tick
from src.db.models import SymbolEnum

logger = logging.getLogger(__name__)


class IBMarketData(BaseMarketData):
    """Interactive Brokers market data implementation."""

    def __init__(self, ib: IB):
        self._ib = ib
        self._tick_callbacks: list[Callable[[Tick], None]] = []
        self._bar_callbacks: list[Callable[[SymbolEnum, Bar], None]] = []
        self._subscriptions: dict[SymbolEnum, Contract] = {}
        self._realtime_bars: dict[SymbolEnum, list] = {}

    async def connect(self) -> None:
        logger.info("IB market data ready (uses shared IB connection)")

    async def disconnect(self) -> None:
        for symbol in list(self._subscriptions.keys()):
            await self.unsubscribe(symbol)
        logger.info("IB market data disconnected")

    async def subscribe(self, symbol: SymbolEnum) -> None:
        if symbol in self._subscriptions:
            return

        contract = make_ib_contract(symbol)
        self._ib.qualifyContracts(contract)
        self._subscriptions[symbol] = contract

        # Request streaming tick data
        self._ib.reqMktData(contract, "", False, False)

        # Request 5-second real-time bars
        bars = self._ib.reqRealTimeBars(contract, 5, "TRADES", False)
        self._realtime_bars[symbol] = bars

        # Set up tick handler
        ticker = self._ib.ticker(contract)
        if ticker:
            ticker.updateEvent += lambda t: self._handle_tick(symbol, t)

        logger.info("Subscribed to %s market data", symbol.value)

    async def unsubscribe(self, symbol: SymbolEnum) -> None:
        contract = self._subscriptions.pop(symbol, None)
        if contract:
            self._ib.cancelMktData(contract)
            if symbol in self._realtime_bars:
                self._ib.cancelRealTimeBars(self._realtime_bars.pop(symbol))
            logger.info("Unsubscribed from %s market data", symbol.value)

    async def get_historical_bars(
        self,
        symbol: SymbolEnum,
        bar_size: str,
        duration: str,
    ) -> list[Bar]:
        contract = make_ib_contract(symbol)
        self._ib.qualifyContracts(contract)

        bars = self._ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=False,
            formatDate=2,
        )

        return [
            Bar(
                timestamp=bar.date if isinstance(bar.date, datetime) else datetime.fromisoformat(str(bar.date)),
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=int(bar.volume),
            )
            for bar in bars
        ]

    def on_tick(self, callback: Callable[[Tick], None]) -> None:
        self._tick_callbacks.append(callback)

    def on_bar(self, callback: Callable[[SymbolEnum, Bar], None]) -> None:
        self._bar_callbacks.append(callback)

    def _handle_tick(self, symbol: SymbolEnum, ticker) -> None:
        tick = Tick(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            price=ticker.last if ticker.last == ticker.last else ticker.close,
            bid=ticker.bid if ticker.bid == ticker.bid else 0.0,
            ask=ticker.ask if ticker.ask == ticker.ask else 0.0,
            volume=int(ticker.volume) if ticker.volume == ticker.volume else 0,
        )
        for cb in self._tick_callbacks:
            try:
                cb(tick)
            except Exception:
                logger.exception("Error in tick callback")
