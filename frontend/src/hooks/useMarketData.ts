"use client";

import { useState, useEffect, useRef } from "react";
import { getCandles } from "@/lib/api";
import { getTimezoneOffsetSec } from "@/lib/timezone";
import type { Candle, Symbol, TickData } from "@/lib/types";
import { useWebSocket } from "./useWebSocket";

// Bar size in seconds for aggregation
export const BAR_SIZES: Record<string, number> = {
  "1 min": 60,
  "5 mins": 300,
  "15 mins": 900,
  "1 hour": 3600,
  "4 hours": 14400,
  "1 day": 86400,
};

function toLocalEpoch(utcEpoch: number): number {
  return utcEpoch + getTimezoneOffsetSec();
}

function floorToBar(timestamp: number, barSeconds: number): number {
  return Math.floor(timestamp / barSeconds) * barSeconds;
}

// Module-level cache — survives page navigations within SPA
type CacheKey = `${Symbol}|${string}|${string}`;
const candleCache = new Map<CacheKey, Candle[]>();
const tickCache = new Map<Symbol, TickData>();
const loadedKeys = new Set<CacheKey>();

function cacheKey(symbol: Symbol, barSize: string, duration: string): CacheKey {
  return `${symbol}|${barSize}|${duration}`;
}

export function useMarketData(symbol: Symbol, barSize = "5 mins", duration = "1 D") {
  const key = cacheKey(symbol, barSize, duration);
  const cached = candleCache.get(key);
  const cachedTick = tickCache.get(symbol);

  const [candles, setCandles] = useState<Candle[]>(cached || []);
  const [lastTick, setLastTick] = useState<TickData | null>(cachedTick || null);
  const [loading, setLoading] = useState(!cached);
  const { subscribe } = useWebSocket();
  const barSeconds = BAR_SIZES[barSize] || 300;
  const historicalLoaded = useRef(loadedKeys.has(key));

  // Fetch historical candles — always re-fetch on timeframe change to get fresh data
  const prevKey = useRef(key);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => {
    const keyChanged = prevKey.current !== key;
    prevKey.current = key;

    // If switching timeframe, invalidate the old cache and force a full reload
    if (keyChanged) {
      historicalLoaded.current = false;
    }

    // Use cache only for initial mount (same key), not for timeframe switches
    if (!keyChanged && candleCache.has(key)) {
      setCandles([...candleCache.get(key)!]); // spread to create new reference
      setLoading(false);
      historicalLoaded.current = true;
      return;
    }

    // Abort any in-flight request for this chart
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    historicalLoaded.current = false;
    setLoading(true);

    const fetchWithRetry = async (retries = 1) => {
      for (let attempt = 0; attempt <= retries; attempt++) {
        if (controller.signal.aborted) return;
        try {
          const res = await getCandles(symbol, barSize, duration, controller.signal);
          if (controller.signal.aborted) return;
          const data = res.candles.map((c) => ({ ...c, time: toLocalEpoch(c.time) }));
          if (data.length > 0) {
            candleCache.set(key, data);
            loadedKeys.add(key);
            setCandles(data);
            historicalLoaded.current = true;
            setLoading(false);
            return;
          }
          // Empty response — retry after short delay
          if (attempt < retries) await new Promise((r) => setTimeout(r, 1000));
        } catch (err) {
          if (controller.signal.aborted) return;
          if (attempt < retries) {
            await new Promise((r) => setTimeout(r, 1000));
          } else {
            console.error(`Failed to load ${symbol} ${barSize} candles:`, err);
          }
        }
      }
      setLoading(false);
    };

    fetchWithRetry(2);

    return () => controller.abort();
  }, [symbol, barSize, duration, key]);

  // Subscribe to real-time tick updates
  useEffect(() => {
    const unsub = subscribe("tick", (data) => {
      const tick = data as TickData;
      if (tick.symbol === symbol) {
        tickCache.set(symbol, tick);
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

        const barTime = floorToBar(toLocalEpoch(bar.time), barSeconds);
        const last = prev[prev.length - 1];

        let updated: Candle[];
        if (last && last.time === barTime) {
          // Update existing bar — add incremental volume delta
          updated = [
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
          updated = [
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
        } else {
          return prev;
        }

        // Update the cache
        candleCache.set(key, updated);
        return updated;
      });
    });
    return unsub;
  }, [symbol, barSeconds, subscribe, key]);

  return { candles, lastTick, loading };
}
