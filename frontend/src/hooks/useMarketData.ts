"use client";

import { useState, useEffect, useCallback } from "react";
import { getCandles } from "@/lib/api";
import type { Candle, Symbol, TickData } from "@/lib/types";
import { useWebSocket } from "./useWebSocket";

export function useMarketData(symbol: Symbol, barSize = "5 mins", duration = "1 D") {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [lastTick, setLastTick] = useState<TickData | null>(null);
  const [loading, setLoading] = useState(true);
  const { subscribe } = useWebSocket();

  // Fetch historical candles
  useEffect(() => {
    setLoading(true);
    getCandles(symbol, barSize, duration)
      .then((res) => setCandles(res.candles))
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

  // Subscribe to candle updates
  useEffect(() => {
    const unsub = subscribe("candle", (data) => {
      const candle = data as Candle & { symbol: Symbol };
      if (candle.symbol === symbol) {
        setCandles((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.time === candle.time) {
            // Update existing candle
            return [...prev.slice(0, -1), candle];
          }
          // New candle
          return [...prev, candle];
        });
      }
    });
    return unsub;
  }, [symbol, subscribe]);

  return { candles, lastTick, loading };
}
