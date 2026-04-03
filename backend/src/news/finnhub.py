import asyncio
import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Callable

import finnhub

from src.config import settings
from src.news.base import BaseNewsProvider, NewsItem

logger = logging.getLogger(__name__)

# Symbols to monitor for ES/NQ-relevant news
MONITORED_SYMBOLS = ["SPY", "QQQ", "ES_F", "NQ_F"]
GENERAL_CATEGORIES = ["general", "forex", "merger"]


class FinnhubNewsProvider(BaseNewsProvider):
    """Finnhub news provider implementation."""

    def __init__(self):
        self._client: finnhub.Client | None = None
        self._callbacks: list[Callable[[NewsItem], None]] = []
        self._polling_task: asyncio.Task | None = None
        self._seen_ids: OrderedDict[str, None] = OrderedDict()
        self._poll_interval: int = 5  # seconds (Finnhub free tier: 60 calls/min, 4 symbols + general = 5 calls/cycle = 12 cycles/min)

    async def connect(self) -> None:
        if not settings.finnhub_api_key:
            logger.warning("Finnhub API key not set, news provider disabled")
            return

        self._client = finnhub.Client(api_key=settings.finnhub_api_key)
        self._polling_task = asyncio.create_task(self._poll_loop())
        logger.info("Finnhub news provider connected")

    async def disconnect(self) -> None:
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        self._client = None
        logger.info("Finnhub news provider disconnected")

    async def get_news(self, symbol: str | None = None, limit: int = 50) -> list[NewsItem]:
        if not self._client:
            return []

        now = datetime.now(timezone.utc)
        from_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")

        try:
            if symbol:
                raw_news = await asyncio.to_thread(
                    self._client.company_news, symbol, _from=from_date, to=to_date
                )
            else:
                raw_news = await asyncio.to_thread(
                    self._client.general_news, "general", min_id=0
                )

            items = []
            for item in raw_news[:limit]:
                news_item = self._parse_item(item)
                if news_item:
                    items.append(news_item)
            return items
        except Exception:
            logger.exception("Error fetching Finnhub news")
            return []

    def on_news(self, callback: Callable[[NewsItem], None]) -> None:
        self._callbacks.append(callback)

    async def _poll_loop(self) -> None:
        """Poll for new news at regular intervals."""
        while True:
            try:
                await self._check_new_news()
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in news polling loop")
                await asyncio.sleep(self._poll_interval)

    async def _check_new_news(self) -> None:
        if not self._client:
            return

        for symbol in MONITORED_SYMBOLS:
            items = await self.get_news(symbol=symbol, limit=10)
            for item in items:
                if item.id not in self._seen_ids:
                    self._seen_ids[item.id] = None
                    for cb in self._callbacks:
                        try:
                            cb(item)
                        except Exception:
                            logger.exception("Error in news callback")

        # Prevent unbounded growth — remove oldest entries
        while len(self._seen_ids) > 10000:
            self._seen_ids.popitem(last=False)

    def _parse_item(self, raw: dict) -> NewsItem | None:
        try:
            timestamp = datetime.fromtimestamp(raw.get("datetime", 0), tz=timezone.utc)
            return NewsItem(
                id=str(raw.get("id", raw.get("datetime", ""))),
                timestamp=timestamp,
                source=raw.get("source", "finnhub"),
                headline=raw.get("headline", ""),
                summary=raw.get("summary", ""),
                symbols=raw.get("related", "").split(",") if raw.get("related") else [],
                url=raw.get("url"),
                raw_payload=raw,
            )
        except Exception:
            logger.exception("Error parsing Finnhub news item")
            return None
