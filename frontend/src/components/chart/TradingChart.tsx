"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  ColorType,
  type CandlestickData,
  type Time,
  type SeriesMarker,
  type HistogramData,
} from "lightweight-charts";
import type { Candle } from "@/lib/types";
import { formatDate, getTimezoneOffsetSec } from "@/lib/timezone";

// RTH is always 9:30 AM - 4:00 PM Eastern Time
// Pre-compute ET offset in seconds from UTC
function getETOffsetSec(): number {
  const now = new Date();
  const utcStr = now.toLocaleString("en-US", { timeZone: "UTC" });
  const etStr = now.toLocaleString("en-US", { timeZone: "America/New_York" });
  return (new Date(etStr).getTime() - new Date(utcStr).getTime()) / 1000;
}
const ET_OFFSET_SEC = getETOffsetSec();

function isRTH(localEpoch: number): boolean {
  // localEpoch is shifted by display TZ. Undo that, apply ET offset instead.
  const displayOffset = getTimezoneOffsetSec();
  const utcEpoch = localEpoch - displayOffset;
  const etEpoch = utcEpoch + ET_OFFSET_SEC;
  const d = new Date(etEpoch * 1000);
  const totalMin = d.getUTCHours() * 60 + d.getUTCMinutes();
  return totalMin >= 570 && totalMin < 960; // 9:30=570, 16:00=960
}

interface TradingChartProps {
  candles: Candle[];
  height?: number;
  markers?: Array<{
    time: number;
    position: "aboveBar" | "belowBar";
    color: string;
    shape: "arrowUp" | "arrowDown" | "circle";
    text: string;
  }>;
  horizontalLines?: Array<{
    price: number;
    color: string;
    lineStyle: number;
    title: string;
  }>;
  /** Unique key for this chart + timeframe combo, used to persist zoom level */
  viewKey?: string;
  /** Bar size in seconds — affects x-axis label formatting */
  barSizeSec?: number;
  /** Synced visible range from the other chart */
  syncRange?: { from: number; to: number } | null;
  /** Callback when this chart's visible range changes (for syncing) */
  onRangeChange?: (range: { from: number; to: number }) => void;
}

// Module-level zoom state per viewKey (bars visible from the right)
const savedVisibleBars: Record<string, number> = {};

export default function TradingChart({
  candles,
  height = 400,
  markers = [],
  horizontalLines = [],
  viewKey,
  barSizeSec = 300,
  syncRange,
  onRangeChange,
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const rthBgSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const markersRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const priceLinesRef = useRef<any[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const applySyncRef = useRef<((range: { from: number; to: number }) => void) | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0f1117" },
        textColor: "#d1d4dc",
      },
      grid: {
        vertLines: { color: "#1e222d" },
        horzLines: { color: "#1e222d" },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: "#2a2e39",
      },
      timeScale: {
        borderColor: "#2a2e39",
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: number) => {
          const d = new Date(time * 1000);
          const h = d.getUTCHours();
          const m = d.getUTCMinutes();

          // Daily: always show date
          if (barSizeSec >= 86400) {
            return formatDate(time);
          }
          // 4h: show "Apr 2" at midnight, "Apr 2 12:00" otherwise
          if (barSizeSec >= 14400) {
            if (h === 0 && m === 0) return formatDate(time);
            return `${formatDate(time)} ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
          }
          // Intraday: show date at midnight, time otherwise
          if (h === 0 && m === 0) {
            return formatDate(time);
          }
          return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
        },
      },
      height,
    });

    // RTH background shading — histogram that fills full height for non-RTH bars
    // Added BEFORE candlestick series so it renders behind
    const rthBgSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: "rthBg",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("rthBg").applyOptions({
      scaleMargins: { top: 0, bottom: 0 },
      visible: false,
    });

    // Candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });

    // Volume histogram series (overlaid at bottom)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    rthBgSeriesRef.current = rthBgSeries;

    // Create markers plugin
    markersRef.current = createSeriesMarkers(candleSeries, []);

    // Sync: notify parent when visible range changes (scroll/zoom)
    // Flags to prevent saving during programmatic range changes
    let applyingSync = false;
    let suppressSave = true; // suppress during initial data load
    setTimeout(() => { suppressSave = false; }, 500);

    applySyncRef.current = (range: { from: number; to: number }) => {
      applyingSync = true;
      chart.timeScale().setVisibleLogicalRange(range);
      if (viewKey) savedVisibleBars[viewKey] = Math.round(range.to - range.from);
      setTimeout(() => { applyingSync = false; }, 100);
    };

    if (onRangeChange) {
      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range && !applyingSync) {
          onRangeChange({ from: range.from, to: range.to });
          // Save zoom — but not during initial load or programmatic changes
          if (viewKey && !suppressSave) {
            savedVisibleBars[viewKey] = Math.round(range.to - range.from);
          }
        }
      });
    }

    // Handle resize
    const resizeObserver = new ResizeObserver((entries) => {
      const { width } = entries[0].contentRect;
      chart.applyOptions({ width });
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      rthBgSeriesRef.current = null;
      markersRef.current = null;
      priceLinesRef.current = [];
      initialLoadDone.current = false;
      prevLengthRef.current = 0;
    };
  }, [height, barSizeSec]);

  // Set candle + volume + RTH data
  const prevLengthRef = useRef(0);
  const initialLoadDone = useRef(false);
  const prevFirstTime = useRef<number>(0);
  const prevViewKey = useRef(viewKey || "");
  useEffect(() => {
    if (!candleSeriesRef.current || !chartRef.current || !volumeSeriesRef.current || candles.length === 0) return;

    // Detect timeframe change — if first candle time changed, force full reload
    const firstTime = candles[0].time;
    if (firstTime !== prevFirstTime.current) {
      initialLoadDone.current = false;
      prevLengthRef.current = 0;
      prevFirstTime.current = firstTime;
    }

    const candleData: CandlestickData<Time>[] = candles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    // RTH background — light gray bars for non-RTH periods
    const rthBgData: HistogramData<Time>[] = candles.map((c) => ({
      time: c.time as Time,
      value: isRTH(c.time) ? 0 : 1,
      color: isRTH(c.time) ? "transparent" : "rgba(255, 255, 255, 0.03)",
    }));

    const volumeData: HistogramData<Time>[] = candles.map((c) => ({
      time: c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? "rgba(38, 166, 154, 0.3)" : "rgba(239, 83, 80, 0.3)",
    }));

    if (!initialLoadDone.current || candles.length < prevLengthRef.current) {
      if (rthBgSeriesRef.current) rthBgSeriesRef.current.setData(rthBgData);
      candleSeriesRef.current.setData(candleData);
      volumeSeriesRef.current.setData(volumeData);

      // Restore saved zoom or fit content
      const savedBars = viewKey ? savedVisibleBars[viewKey] : undefined;
      if (savedBars && savedBars > 0) {
        const totalBars = candles.length;
        chartRef.current.timeScale().setVisibleLogicalRange({
          from: totalBars - savedBars,
          to: totalBars,
        });
      } else {
        chartRef.current.timeScale().fitContent();
      }
      initialLoadDone.current = true;
      prevViewKey.current = viewKey || "";
    } else {
      const last = candles[candles.length - 1];
      candleSeriesRef.current.update({
        time: last.time as Time,
        open: last.open,
        high: last.high,
        low: last.low,
        close: last.close,
      });
      if (rthBgSeriesRef.current) {
        rthBgSeriesRef.current.update({
          time: last.time as Time,
          value: isRTH(last.time) ? 0 : 1,
          color: isRTH(last.time) ? "transparent" : "rgba(255, 255, 255, 0.03)",
        });
      }
      volumeSeriesRef.current.update({
        time: last.time as Time,
        value: last.volume,
        color: last.close >= last.open ? "rgba(38, 166, 154, 0.3)" : "rgba(239, 83, 80, 0.3)",
      });
      chartRef.current.timeScale().scrollToRealTime();
    }
    prevLengthRef.current = candles.length;
  }, [candles]);

  // Update markers
  useEffect(() => {
    if (!markersRef.current) return;

    const sorted = [...markers].sort((a, b) => a.time - b.time);
    markersRef.current.setMarkers(
      sorted.map((m) => ({
        time: m.time as Time,
        position: m.position,
        color: m.color,
        shape: m.shape,
        text: m.text,
      })) as SeriesMarker<Time>[]
    );
  }, [markers]);

  // Update horizontal lines (stop/target) — clear old ones first
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    // Remove old price lines
    for (const line of priceLinesRef.current) {
      try { candleSeriesRef.current.removePriceLine(line); } catch { /* ignore */ }
    }
    priceLinesRef.current = [];

    // Add new ones
    for (const line of horizontalLines) {
      const pl = candleSeriesRef.current.createPriceLine({
        price: line.price,
        color: line.color,
        lineWidth: 1,
        lineStyle: line.lineStyle,
        axisLabelVisible: true,
        title: line.title,
      });
      priceLinesRef.current.push(pl);
    }
  }, [horizontalLines]);

  // Apply synced visible range from the other chart
  useEffect(() => {
    if (!syncRange || !applySyncRef.current) return;
    try {
      applySyncRef.current(syncRange);
    } catch { /* ignore */ }
  }, [syncRange]);

  return <div ref={containerRef} className="w-full" />;
}
