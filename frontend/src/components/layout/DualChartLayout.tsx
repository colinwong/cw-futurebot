"use client";

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import TradingChart, { type TradingChartHandle } from "@/components/chart/TradingChart";
import ChartTimeframe, { DURATION_FOR_BAR_SIZE } from "@/components/chart/ChartTimeframe";
import { useMarketData, BAR_SIZES } from "@/hooks/useMarketData";
import { getPositions } from "@/lib/api";
import { getTimezoneOffsetSec } from "@/lib/timezone";
import { useWebSocket } from "@/hooks/useWebSocket";
import type { Symbol } from "@/lib/types";

interface PositionOverlay {
  symbol: string;
  direction: string;
  entry_price: number;
  stop_price: number | null;
  target_price: number | null;
  entry_timestamp: string;
}

// Module-level: persist shared timeframe and indicator visibility across navigations
let savedBarSize = "1 min";

export type IndicatorVisibility = { ema9: boolean; ema21: boolean; ema50: boolean; ema200: boolean; vwap: boolean };
const defaultVis: IndicatorVisibility = { ema9: true, ema21: true, ema50: true, ema200: false, vwap: true };

// Persist to localStorage so settings survive page refresh
const LS_KEY = "futurebot_indicator_vis";
function loadSavedVis(): Record<string, IndicatorVisibility> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}
function persistVis(vis: Record<string, IndicatorVisibility>) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(vis)); } catch {}
}
let savedIndicatorVis: Record<string, IndicatorVisibility> = {};
let _visLoaded = false;

function SymbolChart({
  symbol,
  positions,
  barSize,
  barSizeSec,
  syncRange,
  onRangeChange,
  chartRef,
  indicatorVis,
}: {
  symbol: Symbol;
  positions: PositionOverlay[];
  barSize: string;
  barSizeSec: number;
  syncRange: { from: number; to: number } | null;
  onRangeChange: (range: { from: number; to: number }) => void;
  chartRef?: React.Ref<TradingChartHandle>;
  indicatorVis: IndicatorVisibility;
}) {
  const duration = DURATION_FOR_BAR_SIZE[barSize] || "1 D";
  const { candles, lastTick, loading } = useMarketData(symbol, barSize, duration);

  const { markers, horizontalLines } = useMemo(() => {
    const m: Array<{
      time: number;
      position: "aboveBar" | "belowBar";
      color: string;
      shape: "arrowUp" | "arrowDown" | "circle";
      text: string;
    }> = [];
    const lines: Array<{
      price: number;
      color: string;
      lineStyle: number;
      title: string;
    }> = [];

    for (const pos of positions) {
      if (pos.entry_price > 0) {
        const entryEpoch = Math.floor(new Date(pos.entry_timestamp).getTime() / 1000) + getTimezoneOffsetSec();
        m.push({
          time: entryEpoch,
          position: pos.direction === "LONG" ? "belowBar" : "aboveBar",
          color: pos.direction === "LONG" ? "#26a69a" : "#ef5350",
          shape: pos.direction === "LONG" ? "arrowUp" : "arrowDown",
          text: `${pos.direction} @ ${pos.entry_price.toFixed(2)}`,
        });
        lines.push({ price: pos.entry_price, color: "#4a90d9", lineStyle: 2, title: `Entry ${pos.entry_price.toFixed(2)}` });
      }
      if (pos.stop_price) lines.push({ price: pos.stop_price, color: "#ef5350", lineStyle: 2, title: `Stop ${pos.stop_price.toFixed(2)}` });
      if (pos.target_price) lines.push({ price: pos.target_price, color: "#22d3ee", lineStyle: 2, title: `Target ${pos.target_price.toFixed(2)}` });
    }
    return { markers: m, horizontalLines: lines };
  }, [positions]);

  return (
    <div className="flex flex-col border border-gray-800 rounded">
      <div className="flex items-center justify-between px-3 py-1.5 bg-gray-900 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <span className="font-bold text-sm">{symbol}</span>
          {lastTick && (
            <span className="text-sm font-mono text-gray-300">
              {lastTick.price.toFixed(2)}
            </span>
          )}
        </div>
      </div>
      {loading ? (
        <div className="flex items-center justify-center h-[400px] text-gray-500">
          Loading {symbol} data...
        </div>
      ) : (
        <TradingChart
          ref={chartRef}
          candles={candles}
          height={400}
          markers={markers}
          horizontalLines={horizontalLines}
          viewKey={`${symbol}|${barSize}`}
          barSizeSec={barSizeSec}
          syncRange={syncRange}
          onRangeChange={onRangeChange}
          indicatorVis={indicatorVis}
        />
      )}
    </div>
  );
}

export default function DualChartLayout() {
  const [positions, setPositions] = useState<PositionOverlay[]>([]);
  const [barSize, setBarSize] = useState(savedBarSize);
  const [indicatorVis, setIndicatorVis] = useState<IndicatorVisibility>({ ...defaultVis });
  const { subscribe } = useWebSocket();

  // Load saved indicator visibility from localStorage after hydration
  useEffect(() => {
    if (!_visLoaded) {
      savedIndicatorVis = loadSavedVis();
      _visLoaded = true;
    }
    const saved = savedIndicatorVis[barSize];
    if (saved) setIndicatorVis(saved);
  }, []);
  const esChartRef = useRef<TradingChartHandle>(null);
  const nqChartRef = useRef<TradingChartHandle>(null);

  // Synced visible range between charts
  const [syncRange, setSyncRange] = useState<{ from: number; to: number } | null>(null);
  const syncSource = useRef<string | null>(null);

  const handleTimeframe = useCallback((newBarSize: string, _newDuration: string) => {
    esChartRef.current?.saveZoom();
    nqChartRef.current?.saveZoom();
    setBarSize(newBarSize);
    savedBarSize = newBarSize;
    setIndicatorVis(savedIndicatorVis[newBarSize] || { ...defaultVis });
    setSyncRange(null);
  }, []);

  const toggleIndicator = useCallback((key: keyof IndicatorVisibility) => {
    setIndicatorVis((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      savedIndicatorVis[barSize] = next;
      persistVis(savedIndicatorVis);
      return next;
    });
  }, [barSize]);

  const makeRangeHandler = useCallback((source: string) => (range: { from: number; to: number }) => {
    // Prevent infinite loop: only sync if this chart initiated the change
    if (syncSource.current === source) return;
    syncSource.current = source;
    setSyncRange(range);
    // Reset source after a tick to allow future syncs
    setTimeout(() => { syncSource.current = null; }, 50);
  }, []);

  useEffect(() => {
    getPositions(true)
      .then((res) => setPositions(res.positions as unknown as PositionOverlay[]))
      .catch(console.error);
  }, []);

  useEffect(() => {
    const unsub = subscribe("position", () => {
      getPositions(true)
        .then((res) => setPositions(res.positions as unknown as PositionOverlay[]))
        .catch(console.error);
    });
    return unsub;
  }, [subscribe]);

  const esPositions = useMemo(() => positions.filter((p) => p.symbol === "MES"), [positions]);
  const nqPositions = useMemo(() => positions.filter((p) => p.symbol === "MNQ"), [positions]);
  const barSizeSec = BAR_SIZES[barSize] || 300;
  const esRangeHandler = useMemo(() => makeRangeHandler("MNQ"), [makeRangeHandler]);
  const nqRangeHandler = useMemo(() => makeRangeHandler("MES"), [makeRangeHandler]);

  return (
    <div>
      {/* Shared timeframe selector + indicator toggles */}
      <div className="flex items-center justify-between px-2 pb-1">
        <div className="flex items-center gap-2 text-[10px]">
          {([
            { key: "ema9" as const, label: "EMA9", color: "#f59e0b" },
            { key: "ema21" as const, label: "EMA21", color: "#3b82f6" },
            { key: "ema50" as const, label: "EMA50", color: "#8b5cf6" },
            { key: "ema200" as const, label: "EMA200", color: "#ef4444" },
            { key: "vwap" as const, label: "VWAP", color: "#ec4899" },
          ]).map((ind) => (
            <button
              key={ind.key}
              onClick={() => toggleIndicator(ind.key)}
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded ${
                indicatorVis[ind.key] ? "bg-gray-800" : "bg-gray-900 opacity-40"
              }`}
            >
              <span className="w-3 h-0.5 inline-block" style={{ backgroundColor: ind.color }} />
              {ind.label}
            </button>
          ))}
        </div>
        <ChartTimeframe selected={barSize} onSelect={handleTimeframe} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <SymbolChart
          symbol="MES"
          positions={esPositions}
          barSize={barSize}
          barSizeSec={barSizeSec}
          syncRange={syncRange}
          onRangeChange={esRangeHandler}
          chartRef={esChartRef}
          indicatorVis={indicatorVis}
        />
        <SymbolChart
          symbol="MNQ"
          positions={nqPositions}
          barSize={barSize}
          barSizeSec={barSizeSec}
          syncRange={syncRange}
          onRangeChange={nqRangeHandler}
          chartRef={nqChartRef}
          indicatorVis={indicatorVis}
        />
      </div>
    </div>
  );
}
