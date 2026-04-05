"""Shared indicator computation module. Computes technical indicators from OHLCV bars."""

import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass


@dataclass
class Bar:
    timestamp: float  # epoch seconds
    open: float
    high: float
    low: float
    close: float
    volume: int


def compute_indicators(bars: list[dict], vwap_reset_hour: int = 0) -> dict:
    """Compute all technical indicators from a list of OHLCV bars.

    Args:
        bars: List of dicts with keys: open, high, low, close, volume, time
        vwap_reset_hour: Hour (UTC) to reset VWAP calculation (default midnight)

    Returns:
        Dict of indicator values at the LAST bar:
        {
            "ema_9": float, "ema_21": float, "ema_50": float,
            "rsi_14": float,
            "vwap": float,
            "macd": float, "macd_signal": float, "macd_histogram": float,
            "bb_upper": float, "bb_middle": float, "bb_lower": float,
            "atr_14": float,
            "atr_sma_20": float,  # 20-period SMA of ATR for range detection
        }
    """
    if len(bars) < 50:
        return {}

    df = pd.DataFrame(bars)
    if "time" in df.columns:
        df = df.rename(columns={"time": "timestamp"})

    # EMA
    df["ema_9"] = ta.ema(df["close"], length=9)
    df["ema_21"] = ta.ema(df["close"], length=21)
    df["ema_50"] = ta.ema(df["close"], length=50)

    # RSI
    df["rsi_14"] = ta.rsi(df["close"], length=14)

    # MACD
    macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd_df is not None and not macd_df.empty:
        df["macd"] = macd_df.iloc[:, 0]
        df["macd_histogram"] = macd_df.iloc[:, 1]
        df["macd_signal"] = macd_df.iloc[:, 2]

    # Bollinger Bands
    bb_df = ta.bbands(df["close"], length=20, std=2.0)
    if bb_df is not None and not bb_df.empty:
        df["bb_lower"] = bb_df.iloc[:, 0]
        df["bb_middle"] = bb_df.iloc[:, 1]
        df["bb_upper"] = bb_df.iloc[:, 2]

    # ATR
    df["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    if "atr_14" in df.columns:
        df["atr_sma_20"] = ta.sma(df["atr_14"], length=20)

    # VWAP (simple cumulative — resets at session boundary)
    if "volume" in df.columns and df["volume"].sum() > 0:
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cum_vol = df["volume"].cumsum()
        cum_tp_vol = (typical_price * df["volume"]).cumsum()
        df["vwap"] = cum_tp_vol / cum_vol.replace(0, 1)
    else:
        df["vwap"] = df["close"]  # fallback

    # Extract the last row's values
    last = df.iloc[-1]
    result = {}

    for col in [
        "ema_9", "ema_21", "ema_50",
        "rsi_14",
        "vwap",
        "macd", "macd_signal", "macd_histogram",
        "bb_upper", "bb_middle", "bb_lower",
        "atr_14", "atr_sma_20",
    ]:
        val = last.get(col)
        if val is not None and pd.notna(val):
            result[col] = float(val)

    # Also include recent highs/lows for range detection
    if len(df) >= 8:
        result["recent_8_high"] = float(df["high"].iloc[-8:].max())
        result["recent_8_low"] = float(df["low"].iloc[-8:].min())

    # Session high/low (all bars)
    result["session_high"] = float(df["high"].max())
    result["session_low"] = float(df["low"].min())

    # MACD histogram history (last 3 bars) for crossover detection
    if "macd_histogram" in df.columns:
        hist = df["macd_histogram"].dropna()
        if len(hist) >= 3:
            result["macd_hist_prev1"] = float(hist.iloc[-2])
            result["macd_hist_prev2"] = float(hist.iloc[-3])

    # Price history for pullback detection (last 4 lows/highs)
    if len(df) >= 4:
        result["low_0"] = float(df["low"].iloc[-1])
        result["low_1"] = float(df["low"].iloc[-2])
        result["low_2"] = float(df["low"].iloc[-3])
        result["low_3"] = float(df["low"].iloc[-4])
        result["high_0"] = float(df["high"].iloc[-1])
        result["high_1"] = float(df["high"].iloc[-2])
        result["high_2"] = float(df["high"].iloc[-3])
        result["high_3"] = float(df["high"].iloc[-4])

    return result
