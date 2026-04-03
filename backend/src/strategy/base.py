from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from src.db.models import DirectionEnum, SymbolEnum


@dataclass
class StrategySignal:
    """Output of a strategy evaluation. Includes structured reasoning for the audit trail."""

    strategy_name: str
    symbol: SymbolEnum
    direction: DirectionEnum
    strength: float  # 0.0 - 1.0 confidence
    reasoning: dict = field(default_factory=dict)
    suggested_stop_ticks: int | None = None
    suggested_target_ticks: int | None = None


@dataclass
class StrategyState:
    """Internal state of a strategy, persisted for debugging."""

    indicator_values: dict = field(default_factory=dict)
    conditions_met: dict = field(default_factory=dict)
    notes: str = ""


class BaseStrategy(ABC):
    """Abstract strategy interface.

    All strategies must:
    1. Return StrategySignal with structured reasoning (for audit trail)
    2. Return StrategyState for debugging/logging
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy name."""

    @abstractmethod
    async def evaluate(
        self,
        symbol: SymbolEnum,
        price: float,
        bid: float,
        ask: float,
        volume: int,
        indicators: dict,
        market_context: dict,
        recent_news: list[dict],
    ) -> StrategySignal | None:
        """Evaluate market conditions and optionally produce a signal.

        Args:
            symbol: The futures symbol being evaluated
            price: Current price
            bid: Current bid
            ask: Current ask
            volume: Current volume
            indicators: Pre-computed indicator values (EMA, RSI, VWAP, etc.)
            market_context: Session info, time to open/close, daily range
            recent_news: Recent analyzed news items (with sentiment/impact)

        Returns:
            StrategySignal if conditions are met, None otherwise
        """

    @abstractmethod
    async def get_state(self, symbol: SymbolEnum) -> StrategyState:
        """Return current internal state for logging."""

    async def reset(self, symbol: SymbolEnum) -> None:
        """Reset strategy state for a symbol. Override if needed."""
        pass
