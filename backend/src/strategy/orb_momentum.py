"""Opening Range Breakout with Momentum Confirmation.

Breakout strategy on 5-minute bars. Trades breakout from the first 30 minutes
of Regular Trading Hours (Initial Balance: 9:30-10:00 ET).
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from src.db.models import DirectionEnum, SymbolEnum
from src.strategy.base import BaseStrategy, StrategySignal, StrategyState

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
MAX_STOP = {SymbolEnum.ES: 12.0, SymbolEnum.NQ: 50.0}
IB_EXTENSION = 0.25  # Breakout must extend 25% of IB range beyond boundary


class ORBMomentum(BaseStrategy):
    def __init__(self):
        # Per-symbol Initial Balance tracking
        self._ib_high: dict[SymbolEnum, float | None] = {}
        self._ib_low: dict[SymbolEnum, float | None] = {}
        self._ib_bars: dict[SymbolEnum, list[dict]] = {}
        self._ib_complete: dict[SymbolEnum, bool] = {}
        self._today: str = ""

    @property
    def name(self) -> str:
        return "orb_momentum"

    async def evaluate(
        self, symbol, price, bid, ask, volume, indicators, market_context, recent_news,
    ) -> StrategySignal | None:
        now_et = datetime.now(ET)
        today = now_et.strftime("%Y-%m-%d")

        # Reset IB tracking at start of new day
        if today != self._today:
            self._today = today
            self._ib_high.clear()
            self._ib_low.clear()
            self._ib_bars.clear()
            self._ib_complete.clear()

        # Only active during RTH (9:30 - 15:45 ET)
        current_min = now_et.hour * 60 + now_et.minute
        if current_min < 570 or current_min >= 945:  # Before 9:30 or after 15:45
            return None

        # Phase 1: Building the Initial Balance (9:30 - 10:00 ET)
        if current_min < 600:  # Before 10:00
            high_0 = indicators.get("high_0")
            low_0 = indicators.get("low_0")
            if high_0 and low_0:
                if symbol not in self._ib_high or high_0 > (self._ib_high.get(symbol) or 0):
                    self._ib_high[symbol] = high_0
                if symbol not in self._ib_low or low_0 < (self._ib_low.get(symbol) or float("inf")):
                    self._ib_low[symbol] = low_0
            return None  # No signals during IB formation

        # Mark IB as complete
        if not self._ib_complete.get(symbol):
            self._ib_complete[symbol] = True
            ib_h = self._ib_high.get(symbol)
            ib_l = self._ib_low.get(symbol)
            if ib_h and ib_l:
                logger.info("ORB %s: IB formed — high=%.2f, low=%.2f, range=%.2f",
                            symbol.value, ib_h, ib_l, ib_h - ib_l)

        # Phase 2: Look for breakout (10:00 - 12:00 ET)
        if current_min >= 720:  # After 12:00 — no new entries
            return None

        ib_high = self._ib_high.get(symbol)
        ib_low = self._ib_low.get(symbol)
        if not ib_high or not ib_low:
            return None

        ib_range = ib_high - ib_low
        if ib_range <= 0:
            return None

        rsi = indicators.get("rsi_14")
        ema_9 = indicators.get("ema_9")
        ema_21 = indicators.get("ema_21")

        if any(v is None for v in [rsi, ema_9, ema_21]):
            return None

        breakout_extension = ib_range * IB_EXTENSION
        max_stop = MAX_STOP.get(symbol, 12.0)

        # LONG breakout
        if (
            price > ib_high + breakout_extension      # Price extended above IB
            and rsi > 60                               # Momentum confirmed
            and ema_9 > ema_21                         # EMAs aligned bullish
        ):
            stop_price = max(ib_low, price - max_stop)  # IB low or max stop
            stop_dist = price - stop_price
            target_dist = ib_range  # 1.0x IB range

            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction=DirectionEnum.LONG,
                strength=min(1.0, (rsi - 60) / 20),
                reasoning={
                    "trigger": "Opening Range Breakout — bullish",
                    "ib_high": round(ib_high, 2),
                    "ib_low": round(ib_low, 2),
                    "ib_range": round(ib_range, 2),
                    "rsi": round(rsi, 2),
                    "price": price,
                    "description": (
                        f"Price broke above IB high {ib_high:.2f} + {breakout_extension:.2f} extension. "
                        f"IB range: {ib_range:.2f}. RSI {rsi:.1f}, EMA9 > EMA21. "
                        f"Stop at IB low {stop_price:.2f}, target {price + target_dist:.2f}"
                    ),
                },
                suggested_stop_ticks=int(stop_dist / 0.25),
                suggested_target_ticks=int(target_dist / 0.25),
            )

        # SHORT breakout
        if (
            price < ib_low - breakout_extension        # Price extended below IB
            and rsi < 40                               # Momentum confirmed
            and ema_9 < ema_21                         # EMAs aligned bearish
        ):
            stop_price = min(ib_high, price + max_stop)
            stop_dist = stop_price - price
            target_dist = ib_range

            return StrategySignal(
                strategy_name=self.name,
                symbol=symbol,
                direction=DirectionEnum.SHORT,
                strength=min(1.0, (40 - rsi) / 20),
                reasoning={
                    "trigger": "Opening Range Breakout — bearish",
                    "ib_high": round(ib_high, 2),
                    "ib_low": round(ib_low, 2),
                    "ib_range": round(ib_range, 2),
                    "rsi": round(rsi, 2),
                    "price": price,
                    "description": (
                        f"Price broke below IB low {ib_low:.2f} - {breakout_extension:.2f} extension. "
                        f"IB range: {ib_range:.2f}. RSI {rsi:.1f}, EMA9 < EMA21. "
                        f"Stop at IB high {stop_price:.2f}, target {price - target_dist:.2f}"
                    ),
                },
                suggested_stop_ticks=int(stop_dist / 0.25),
                suggested_target_ticks=int(target_dist / 0.25),
            )

        return None

    async def get_state(self, symbol) -> StrategyState:
        return StrategyState(
            indicator_values={
                "ib_high": self._ib_high.get(symbol),
                "ib_low": self._ib_low.get(symbol),
                "ib_complete": self._ib_complete.get(symbol, False),
            },
            notes="ORB Momentum (5m, RTH only)",
        )
