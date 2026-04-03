from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


@dataclass
class NewsItem:
    """Common news item returned by all providers."""

    id: str
    timestamp: datetime
    source: str
    headline: str
    summary: str
    symbols: list[str] = field(default_factory=list)
    url: str | None = None
    raw_payload: dict = field(default_factory=dict)


class BaseNewsProvider(ABC):
    """Abstract news provider interface. Implement this to add a new provider."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to news provider."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from news provider."""

    @abstractmethod
    async def get_news(self, symbol: str | None = None, limit: int = 50) -> list[NewsItem]:
        """Fetch recent news. Optionally filter by symbol."""

    @abstractmethod
    def on_news(self, callback: Callable[[NewsItem], None]) -> None:
        """Register callback for real-time news delivery."""
