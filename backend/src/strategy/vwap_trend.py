"""VWAP Trend Continuation Strategy.

Trend-following on 5-minute bars. Enters when price pulls back to VWAP
during an established trend and momentum resumes.
"""

import logging

from src.db.models import DirectionEnum, SymbolEnum
from src.strategy.base import BaseStrategy, StrategySignal, StrategyState

logger = logging.getLogger(__name__)

# Stop distances in points (same price action for ES/MES and NQ/MNQ)
STOP_POINTS = {SymbolEnum.ES: 6.0, SymbolEnum.MES: 6.0, SymbolEnum.NQ: 25.0, SymbolEnum.MNQ: 25.0}
TARGET_MULTIPLIER = 1.5  # Target = 1.5x stop distance


class VWAPTrendContinuation(BaseStrategy):
    @property
    def name(self) -> str:
        return "vwap_trend_continuation"

    async def evaluate(
        self, symbol, price, bid, ask, volume, indicators, market_context, recent_news,
    ) -> StrategySignal | None:
        ema_9 = indicators.get("ema_9")
        ema_21 = indicators.get("ema_21")
        ema_50 = indicators.get("ema_50")
        rsi = indicators.get("rsi_14")
        vwap = indicators.get("vwap")
        macd_hist = indicators.get("macd_histogram")
        macd_hist_prev1 = indicators.get("macd_hist_prev1")

        if any(v is None for v in [ema_9, ema_21, ema_50, rsi, vwap, macd_hist]):
            return None

        # Pullback detection: min of last 4 lows near VWAP
        lows = [indicators.get(f"low_{i}") for i in range(4)]
        highs = [indicators.get(f"high_{i}") for i in range(4)]
        if None in lows or None in highs:
            return None

        # Check LONG conditions
        if (
            ema_21 > ema_50                          # Uptrend
            and price > vwap                          # Above VWAP
            and min(lows) <= vwap * 1.0025            # Pullback to VWAP zone
            and 45 <= rsi <= 65                       # RSI recovering, not overbought
            and price > ema_9                         # Close above fast EMA
            and (macd_hist > 0 or (macd_hist_prev1 is not None and macd_hist_prev1 < 0 and macd_hist > 0))
        ):
            stop_pts = STOP_POINTS.get(symbol, 6.0)
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction=DirectionEnum.LONG,
                strength=min(1.0, (rsi - 45) / 20),
                reasoning={
                    "trigger": "VWAP trend continuation — bullish",
                    "ema_21": round(ema_21, 2),
                    "ema_50": round(ema_50, 2),
                    "vwap": round(vwap, 2),
                    "rsi": round(rsi, 2),
                    "macd_histogram": round(macd_hist, 4),
                    "price": price,
                    "description": (
                        f"Uptrend (EMA21 {ema_21:.2f} > EMA50 {ema_50:.2f}), "
                        f"price pulled back to VWAP {vwap:.2f}, "
                        f"RSI {rsi:.1f} recovering, MACD histogram positive"
                    ),
                },
                suggested_stop_ticks=int(stop_pts / 0.25),
                suggested_target_ticks=int(stop_pts * TARGET_MULTIPLIER / 0.25),
            )

        # Check SHORT conditions
        if (
            ema_21 < ema_50                           # Downtrend
            and price < vwap                          # Below VWAP
            and max(highs) >= vwap * 0.9975           # Rally back toward VWAP
            and 35 <= rsi <= 55                       # RSI weakening, not oversold
            and price < ema_9                         # Close below fast EMA
            and (macd_hist < 0 or (macd_hist_prev1 is not None and macd_hist_prev1 > 0 and macd_hist < 0))
        ):
            stop_pts = STOP_POINTS.get(symbol, 6.0)
            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction=DirectionEnum.SHORT,
                strength=min(1.0, (55 - rsi) / 20),
                reasoning={
                    "trigger": "VWAP trend continuation — bearish",
                    "ema_21": round(ema_21, 2),
                    "ema_50": round(ema_50, 2),
                    "vwap": round(vwap, 2),
                    "rsi": round(rsi, 2),
                    "macd_histogram": round(macd_hist, 4),
                    "price": price,
                    "description": (
                        f"Downtrend (EMA21 {ema_21:.2f} < EMA50 {ema_50:.2f}), "
                        f"price rallied to VWAP {vwap:.2f}, "
                        f"RSI {rsi:.1f} weakening, MACD histogram negative"
                    ),
                },
                suggested_stop_ticks=int(stop_pts / 0.25),
                suggested_target_ticks=int(stop_pts * TARGET_MULTIPLIER / 0.25),
            )

        return None

    async def get_state(self, symbol) -> StrategyState:
        return StrategyState(notes="VWAP Trend Continuation (5m)")
