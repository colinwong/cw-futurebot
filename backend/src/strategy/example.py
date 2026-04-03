import logging

from src.db.models import DirectionEnum, SymbolEnum
from src.strategy.base import BaseStrategy, StrategySignal, StrategyState

logger = logging.getLogger(__name__)


class EMACrossoverStrategy(BaseStrategy):
    """Example strategy: EMA crossover with RSI filter.

    Goes long when fast EMA crosses above slow EMA and RSI < 70.
    Goes short when fast EMA crosses below slow EMA and RSI > 30.

    This is a scaffold — replace with real strategy logic.
    """

    @property
    def name(self) -> str:
        return "ema_crossover"

    def __init__(self, fast_period: int = 9, slow_period: int = 21):
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._prev_fast: dict[SymbolEnum, float | None] = {}
        self._prev_slow: dict[SymbolEnum, float | None] = {}

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
        fast_ema = indicators.get(f"ema_{self._fast_period}")
        slow_ema = indicators.get(f"ema_{self._slow_period}")
        rsi = indicators.get("rsi_14")

        if fast_ema is None or slow_ema is None or rsi is None:
            return None

        prev_fast = self._prev_fast.get(symbol)
        prev_slow = self._prev_slow.get(symbol)

        # Update previous values
        self._prev_fast[symbol] = fast_ema
        self._prev_slow[symbol] = slow_ema

        if prev_fast is None or prev_slow is None:
            return None

        # Detect crossover
        was_below = prev_fast < prev_slow
        is_above = fast_ema > slow_ema
        was_above = prev_fast > prev_slow
        is_below = fast_ema < slow_ema

        bullish_cross = was_below and is_above
        bearish_cross = was_above and is_below

        if bullish_cross and rsi < 70:
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction=DirectionEnum.LONG,
                strength=min(1.0, (70 - rsi) / 40),  # Stronger when RSI is lower
                reasoning={
                    "trigger": "EMA bullish crossover",
                    "fast_ema": round(fast_ema, 2),
                    "slow_ema": round(slow_ema, 2),
                    "rsi": round(rsi, 2),
                    "price": price,
                    "description": (
                        f"EMA{self._fast_period} ({fast_ema:.2f}) crossed above "
                        f"EMA{self._slow_period} ({slow_ema:.2f}), RSI at {rsi:.1f}"
                    ),
                },
            )

        if bearish_cross and rsi > 30:
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction=DirectionEnum.SHORT,
                strength=min(1.0, (rsi - 30) / 40),  # Stronger when RSI is higher
                reasoning={
                    "trigger": "EMA bearish crossover",
                    "fast_ema": round(fast_ema, 2),
                    "slow_ema": round(slow_ema, 2),
                    "rsi": round(rsi, 2),
                    "price": price,
                    "description": (
                        f"EMA{self._fast_period} ({fast_ema:.2f}) crossed below "
                        f"EMA{self._slow_period} ({slow_ema:.2f}), RSI at {rsi:.1f}"
                    ),
                },
            )

        return None

    async def get_state(self, symbol: SymbolEnum) -> StrategyState:
        return StrategyState(
            indicator_values={
                "prev_fast_ema": self._prev_fast.get(symbol),
                "prev_slow_ema": self._prev_slow.get(symbol),
            },
            conditions_met={},
            notes=f"EMA crossover strategy (fast={self._fast_period}, slow={self._slow_period})",
        )
