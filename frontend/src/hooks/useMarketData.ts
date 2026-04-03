"use client";

import { useState, useEffect, useRef } from "react";
import { getCandles } from "@/lib/api";
import type { Candle, Symbol, TickData } from "@/lib/types";
import { useWebSocket } from "./useWebSocket";

// Bar size in seconds for aggregation
const BAR_SIZES: Record<string, number> = {
  "1 min": 60,
  "5 mins": 300,
  "15 mins": 900,
  "1 hour": 3600,
  "4 hours": 14400,
  "1 day": 86400,
};

function floorToBar(timestamp: number, barSeconds: number): number {
  return Math.floor(timestamp / barSeconds) * barSeconds;
}

export function useMarketData(symbol: Symbol, barSize = "5 mins", duration = "1 D") {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [lastTick, setLastTick] = useState<TickData | null>(null);
  const [loading, setLoading] = useState(true);
  const { subscribe } = useWebSocket();
  const barSeconds = BAR_SIZES[barSize] || 300;
  const historicalLoaded = useRef(false);

  // Fetch historical candles
  useEffect(() => {
    historicalLoaded.current = false;
    setLoading(true);
    getCandles(symbol, barSize, duration)
      .then((res) => {
        setCandles(res.candles);
        historicalLoaded.current = true;
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [symbol, barSize, duration]);

  // Subscribe to real-time tick updates
  useEffect(() => {
    const unsub = subscribe("tick", (data) => {
      const tick = data as TickData;
      if (tick.symbol === symbol) {
        setLastTick(tick);
      }
    });
    return unsub;
  }, [symbol, subscribe]);

  // Subscribe to 5-second bar updates from IB and aggregate into chart bars
  useEffect(() => {
    const unsub = subscribe("candle", (data) => {
      const bar = data as Candle & { symbol: Symbol };
      if (bar.symbol !== symbol) return;
      if (!historicalLoaded.current) return;

      setCandles((prev) => {
        if (prev.length === 0) return prev;

        const barTime = floorToBar(bar.time, barSeconds);
        const last = prev[prev.length - 1];

        if (last && last.time === barTime) {
          // Update existing candle — extend high/low, update close, add volume
          return [
            ...prev.slice(0, -1),
            {
              time: barTime,
              open: last.open,
              high: Math.max(last.high, bar.high),
              low: Math.min(last.low, bar.low),
              close: bar.close,
              volume: last.volume + bar.volume,
            },
          ];
        } else if (barTime > (last?.time ?? 0)) {
          // New bar period — start a new candle
          return [
            ...prev,
            {
              time: barTime,
              open: bar.open,
              high: bar.high,
              low: bar.low,
              close: bar.close,
              volume: bar.volume,
            },
          ];
        }

        return prev;
      });
    });
    return unsub;
  }, [symbol, barSeconds, subscribe]);

  return { candles, lastTick, loading };
}
