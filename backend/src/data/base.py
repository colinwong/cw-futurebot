from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from src.db.models import SymbolEnum


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class Tick:
    timestamp: datetime
    symbol: SymbolEnum
    price: float
    bid: float
    ask: float
    volume: int


class BaseMarketData(ABC):
    """Abstract market data interface."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to data provider."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from data provider."""

    @abstractmethod
    async def subscribe(self, symbol: SymbolEnum) -> None:
        """Subscribe to real-time data for a symbol."""

    @abstractmethod
    async def unsubscribe(self, symbol: SymbolEnum) -> None:
        """Unsubscribe from real-time data for a symbol."""

    @abstractmethod
    async def get_historical_bars(
        self,
        symbol: SymbolEnum,
        bar_size: str,
        duration: str,
    ) -> list[Bar]:
        """Get historical OHLCV bars.

        Args:
            symbol: The futures symbol
            bar_size: Bar size (e.g., "1 min", "5 mins", "1 hour", "1 day")
            duration: How far back (e.g., "1 D", "1 W", "1 M")
        """

    @abstractmethod
    def on_tick(self, callback: Callable[[Tick], None]) -> None:
        """Register callback for real-time tick updates."""

    @abstractmethod
    def on_bar(self, callback: Callable[[SymbolEnum, Bar], None]) -> None:
        """Register callback for completed bar updates."""
