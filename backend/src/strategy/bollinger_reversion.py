"""Bollinger Band Mean Reversion Strategy.

Mean-reversion on 15-minute bars. Fades price extremes at Bollinger Bands
during range-bound sessions.
"""

import logging

from src.db.models import DirectionEnum, SymbolEnum
from src.strategy.base import BaseStrategy, StrategySignal, StrategyState

logger = logging.getLogger(__name__)

STOP_BEYOND_BAND = {SymbolEnum.ES: 4.0, SymbolEnum.NQ: 18.0}


class BollingerMeanReversion(BaseStrategy):
    @property
    def name(self) -> str:
        return "bollinger_mean_reversion"

    async def evaluate(
        self, symbol, price, bid, ask, volume, indicators, market_context, recent_news,
    ) -> StrategySignal | None:
        bb_upper = indicators.get("bb_upper")
        bb_lower = indicators.get("bb_lower")
        bb_middle = indicators.get("bb_middle")
        rsi = indicators.get("rsi_14")
        ema_21 = indicators.get("ema_21")
        ema_50 = indicators.get("ema_50")
        atr = indicators.get("atr_14")
        atr_sma = indicators.get("atr_sma_20")
        recent_high = indicators.get("recent_8_high")
        recent_low = indicators.get("recent_8_low")
        session_high = indicators.get("session_high")
        session_low = indicators.get("session_low")
        low_0 = indicators.get("low_0")
        high_0 = indicators.get("high_0")

        if any(v is None for v in [bb_upper, bb_lower, bb_middle, rsi, ema_21, ema_50, atr]):
            return None

        # Range detection filter
        if atr_sma is not None and atr > atr_sma:
            return None  # Volatility expanding, not a range

        if recent_high is not None and session_high is not None:
            if recent_high >= session_high:
                return None  # New session high in last 8 bars — trending, not ranging

        if recent_low is not None and session_low is not None:
            if recent_low <= session_low:
                return None  # New session low in last 8 bars

        # EMAs must be converged (flat market)
        if ema_50 > 0 and abs(ema_21 - ema_50) / ema_50 > 0.0015:
            return None  # EMAs diverging — not a range

        # LONG: price at lower Bollinger Band with bullish rejection
        if low_0 is not None and low_0 <= bb_lower and rsi < 30:
            # Check for rejection candle: close in upper 60% of range
            bar_range = high_0 - low_0 if high_0 and low_0 else 0
            if bar_range > 0 and (price - low_0) / bar_range >= 0.60:
                stop_pts = STOP_BEYOND_BAND.get(symbol, 4.0)
                # Cap stop at 1.5x ATR
                if atr and stop_pts > 1.5 * atr:
                    return None  # Band too wide

                target_dist = bb_middle - price if bb_middle > price else stop_pts
                return StrategySignal(
                    strategy_name=self.name,
                    symbol=symbol,
                    direction=DirectionEnum.LONG,
                    strength=min(1.0, (30 - rsi) / 15),
                    reasoning={
                        "trigger": "Bollinger mean reversion — oversold bounce",
                        "bb_lower": round(bb_lower, 2),
                        "bb_middle": round(bb_middle, 2),
                        "rsi": round(rsi, 2),
                        "atr": round(atr, 2),
                        "price": price,
                        "description": (
                            f"Price touched lower BB {bb_lower:.2f} with RSI {rsi:.1f} oversold, "
                            f"bullish rejection candle, range-bound market (EMAs converged). "
                            f"Target: middle BB {bb_middle:.2f}"
                        ),
                    },
                    suggested_stop_ticks=int(stop_pts / 0.25),
                    suggested_target_ticks=int(target_dist / 0.25),
                )

        # SHORT: price at upper Bollinger Band with bearish rejection
        if high_0 is not None and high_0 >= bb_upper and rsi > 70:
            bar_range = high_0 - low_0 if high_0 and low_0 else 0
            if bar_range > 0 and (high_0 - price) / bar_range >= 0.60:
                stop_pts = STOP_BEYOND_BAND.get(symbol, 4.0)
                if atr and stop_pts > 1.5 * atr:
                    return None

                target_dist = price - bb_middle if price > bb_middle else stop_pts
                return StrategySignal(
                    strategy_name=self.name,
                    symbol=symbol,
                    direction=DirectionEnum.SHORT,
                    strength=min(1.0, (rsi - 70) / 15),
                    reasoning={
                        "trigger": "Bollinger mean reversion — overbought fade",
                        "bb_upper": round(bb_upper, 2),
                        "bb_middle": round(bb_middle, 2),
                        "rsi": round(rsi, 2),
                        "atr": round(atr, 2),
                        "price": price,
                        "description": (
                            f"Price touched upper BB {bb_upper:.2f} with RSI {rsi:.1f} overbought, "
                            f"bearish rejection candle, range-bound market. "
                            f"Target: middle BB {bb_middle:.2f}"
                        ),
                    },
                    suggested_stop_ticks=int(stop_pts / 0.25),
                    suggested_target_ticks=int(target_dist / 0.25),
                )

        return None

    async def get_state(self, symbol) -> StrategyState:
        return StrategyState(notes="Bollinger Mean Reversion (15m)")
