"use client";

import { useEffect, useRef, useImperativeHandle, forwardRef } from "react";
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
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
function getETOffsetSec(): number {
  const now = new Date();
  const utcStr = now.toLocaleString("en-US", { timeZone: "UTC" });
  const etStr = now.toLocaleString("en-US", { timeZone: "America/New_York" });
  return (new Date(etStr).getTime() - new Date(utcStr).getTime()) / 1000;
}
const ET_OFFSET_SEC = getETOffsetSec();

function isRTH(localEpoch: number): boolean {
  return isRTHCached(localEpoch, getTimezoneOffsetSec());
}

function isRTHCached(localEpoch: number, displayOffset: number): boolean {
  const etEpoch = localEpoch - displayOffset + ET_OFFSET_SEC;
  const d = new Date(etEpoch * 1000);
  const totalMin = d.getUTCHours() * 60 + d.getUTCMinutes();
  return totalMin >= 570 && totalMin < 960;
}

// Simple EMA calculation from candle closes
function computeEMA(candles: Candle[], period: number): { time: number; value: number }[] {
  if (candles.length < period) return [];
  const k = 2 / (period + 1);
  const result: { time: number; value: number }[] = [];
  let ema = candles.slice(0, period).reduce((s, c) => s + c.close, 0) / period;
  for (let i = period - 1; i < candles.length; i++) {
    ema = candles[i].close * k + ema * (1 - k);
    result.push({ time: candles[i].time, value: ema });
  }
  return result;
}

// Simple VWAP from candle data
function computeVWAP(candles: Candle[]): { time: number; value: number }[] {
  let cumVol = 0;
  let cumTPVol = 0;
  const result: { time: number; value: number }[] = [];
  for (const c of candles) {
    const tp = (c.high + c.low + c.close) / 3;
    cumVol += c.volume;
    cumTPVol += tp * c.volume;
    if (cumVol > 0) {
      result.push({ time: c.time, value: cumTPVol / cumVol });
    }
  }
  return result;
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
  viewKey?: string;
  barSizeSec?: number;
  syncRange?: { from: number; to: number } | null;
  onRangeChange?: (range: { from: number; to: number }) => void;
  showIndicators?: boolean;
  indicatorVis?: { ema9: boolean; ema21: boolean; ema50: boolean; ema200: boolean; vwap: boolean };
}

export interface TradingChartHandle {
  saveZoom: () => void;
}

// Module-level zoom state per viewKey
const savedVisibleBars: Record<string, number> = {};

const TradingChart = forwardRef<TradingChartHandle, TradingChartProps>(function TradingChart({
  candles,
  height = 400,
  markers = [],
  horizontalLines = [],
  viewKey,
  barSizeSec = 300,
  syncRange,
  onRangeChange,
  showIndicators = true,
  indicatorVis = { ema9: true, ema21: true, ema50: true, ema200: false, vwap: true },
}, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const rthBgSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ema9Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema21Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema200Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const vwapRef = useRef<ISeriesApi<"Line"> | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const markersRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const priceLinesRef = useRef<any[]>([]);

  // Expose saveZoom to parent
  useImperativeHandle(ref, () => ({
    saveZoom: () => {
      if (!chartRef.current || !viewKey) return;
      try {
        const range = chartRef.current.timeScale().getVisibleLogicalRange();
        if (range) {
          savedVisibleBars[viewKey] = Math.round(range.to - range.from);
        }
      } catch { /* ignore */ }
    },
  }), [viewKey]);

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
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: "#2a2e39" },
      timeScale: {
        borderColor: "#2a2e39",
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: number) => {
          const d = new Date(time * 1000);
          const h = d.getUTCHours();
          const m = d.getUTCMinutes();
          if (barSizeSec >= 86400) return formatDate(time);
          if (barSizeSec >= 14400) {
            if (h === 0 && m === 0) return formatDate(time);
            return `${formatDate(time)} ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
          }
          if (h === 0 && m === 0) return formatDate(time);
          return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
        },
      },
      height,
    });

    const rthBgSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: "rthBg",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("rthBg").applyOptions({
      scaleMargins: { top: 0, bottom: 0 },
      visible: false,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    // Indicator overlay lines
    let ema9Series: ISeriesApi<"Line"> | null = null;
    let ema21Series: ISeriesApi<"Line"> | null = null;
    let ema50Series: ISeriesApi<"Line"> | null = null;
    let ema200Series: ISeriesApi<"Line"> | null = null;
    let vwapSeries: ISeriesApi<"Line"> | null = null;
    if (showIndicators) {
      ema9Series = chart.addSeries(LineSeries, {
        color: "#f59e0b", lineWidth: 1, lastValueVisible: false, priceLineVisible: false,
      });
      ema21Series = chart.addSeries(LineSeries, {
        color: "#3b82f6", lineWidth: 1, lastValueVisible: false, priceLineVisible: false,
      });
      ema50Series = chart.addSeries(LineSeries, {
        color: "#8b5cf6", lineWidth: 1, lastValueVisible: false, priceLineVisible: false,
      });
      ema200Series = chart.addSeries(LineSeries, {
        color: "#ef4444", lineWidth: 1, lastValueVisible: false, priceLineVisible: false,
      });
      vwapSeries = chart.addSeries(LineSeries, {
        color: "#ec4899", lineWidth: 1, lineStyle: 2, lastValueVisible: false, priceLineVisible: false,
      });
    }

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    rthBgSeriesRef.current = rthBgSeries;
    ema9Ref.current = ema9Series;
    ema21Ref.current = ema21Series;
    ema50Ref.current = ema50Series;
    ema200Ref.current = ema200Series;
    vwapRef.current = vwapSeries;
    markersRef.current = createSeriesMarkers(candleSeries, []);

    // Sync: notify parent when user scrolls/zooms (not during programmatic changes)
    let programmatic = false;

    if (onRangeChange) {
      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range && !programmatic) {
          onRangeChange({ from: range.from, to: range.to });
          if (viewKey) savedVisibleBars[viewKey] = Math.round(range.to - range.from);
        }
      });
    }

    // Helper to set range without triggering sync
    const setRangeSilently = (range: { from: number; to: number }) => {
      programmatic = true;
      chart.timeScale().setVisibleLogicalRange(range);
      setTimeout(() => { programmatic = false; }, 50);
    };

    // Store for sync effect
    setRangeSilentlyRef.current = setRangeSilently;
    fitContentSilentlyRef.current = () => {
      programmatic = true;
      chart.timeScale().fitContent();
      setTimeout(() => { programmatic = false; }, 50);
    };

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
      ema9Ref.current = null;
      ema21Ref.current = null;
      ema50Ref.current = null;
      ema200Ref.current = null;
      vwapRef.current = null;
      markersRef.current = null;
      priceLinesRef.current = [];
      initialLoadDone.current = false;
      prevLengthRef.current = 0;
      setRangeSilentlyRef.current = null;
      fitContentSilentlyRef.current = null;
      visInitialized.current = false;
    };
  }, [height, barSizeSec]);

  const prevLengthRef = useRef(0);
  const initialLoadDone = useRef(false);
  const prevFirstTime = useRef<number>(0);
  const setRangeSilentlyRef = useRef<((r: { from: number; to: number }) => void) | null>(null);
  const fitContentSilentlyRef = useRef<(() => void) | null>(null);

  // Set candle + volume + RTH data
  useEffect(() => {
    if (!candleSeriesRef.current || !chartRef.current || !volumeSeriesRef.current || candles.length === 0) return;

    const firstTime = candles[0].time;
    if (firstTime !== prevFirstTime.current) {
      initialLoadDone.current = false;
      prevLengthRef.current = 0;
      prevFirstTime.current = firstTime;
    }

    if (!initialLoadDone.current || candles.length < prevLengthRef.current) {
      // Full data load — build all arrays (cache displayOffset to avoid N calls)
      const displayOffset = getTimezoneOffsetSec();
      const candleData: CandlestickData<Time>[] = candles.map((c) => ({
        time: c.time as Time, open: c.open, high: c.high, low: c.low, close: c.close,
      }));
      const rthBgData: HistogramData<Time>[] = candles.map((c) => {
        const rth = isRTHCached(c.time, displayOffset);
        return { time: c.time as Time, value: rth ? 0 : 1, color: rth ? "transparent" : "rgba(255, 255, 255, 0.03)" };
      });
      const volumeData: HistogramData<Time>[] = candles.map((c) => ({
        time: c.time as Time, value: c.volume,
        color: c.close >= c.open ? "rgba(38, 166, 154, 0.3)" : "rgba(239, 83, 80, 0.3)",
      }));

      if (rthBgSeriesRef.current) rthBgSeriesRef.current.setData(rthBgData);
      candleSeriesRef.current.setData(candleData);
      volumeSeriesRef.current.setData(volumeData);

      // Compute and set indicator overlays based on visibility
      if (showIndicators) {
        const toLineData = (pts: { time: number; value: number }[]) =>
          pts.map((p) => ({ time: p.time as Time, value: p.value }));
        const empty: { time: Time; value: number }[] = [];
        if (ema9Ref.current) ema9Ref.current.setData(indicatorVis.ema9 ? toLineData(computeEMA(candles, 9)) : empty);
        if (ema21Ref.current) ema21Ref.current.setData(indicatorVis.ema21 ? toLineData(computeEMA(candles, 21)) : empty);
        if (ema50Ref.current) ema50Ref.current.setData(indicatorVis.ema50 ? toLineData(computeEMA(candles, 50)) : empty);
        if (ema200Ref.current) ema200Ref.current.setData(indicatorVis.ema200 ? toLineData(computeEMA(candles, 200)) : empty);
        if (vwapRef.current) vwapRef.current.setData(indicatorVis.vwap ? toLineData(computeVWAP(candles)) : empty);
      }

      const saved = viewKey ? savedVisibleBars[viewKey] : undefined;
      if (saved && saved > 0 && setRangeSilentlyRef.current) {
        setRangeSilentlyRef.current({ from: candles.length - saved, to: candles.length });
      } else if (fitContentSilentlyRef.current) {
        fitContentSilentlyRef.current();
      }
      initialLoadDone.current = true;
    } else {
      // Incremental update — only update the last candle
      const last = candles[candles.length - 1];
      const rth = isRTH(last.time);
      candleSeriesRef.current.update({
        time: last.time as Time, open: last.open, high: last.high, low: last.low, close: last.close,
      });
      if (rthBgSeriesRef.current) {
        rthBgSeriesRef.current.update({
          time: last.time as Time, value: rth ? 0 : 1, color: rth ? "transparent" : "rgba(255, 255, 255, 0.03)",
        });
      }
      volumeSeriesRef.current.update({
        time: last.time as Time, value: last.volume,
        color: last.close >= last.open ? "rgba(38, 166, 154, 0.3)" : "rgba(239, 83, 80, 0.3)",
      });
      chartRef.current.timeScale().scrollToRealTime();
    }
    prevLengthRef.current = candles.length;
  }, [candles]);

  // Update indicator visibility when toggled (skip initial — data effect handles that)
  const visInitialized = useRef(false);
  useEffect(() => {
    if (!visInitialized.current) {
      visInitialized.current = true;
      return;
    }
    if (!showIndicators || candles.length === 0) return;
    const toLineData = (pts: { time: number; value: number }[]) =>
      pts.map((p) => ({ time: p.time as Time, value: p.value }));
    const empty: { time: Time; value: number }[] = [];
    if (ema9Ref.current) ema9Ref.current.setData(indicatorVis.ema9 && candles.length > 9 ? toLineData(computeEMA(candles, 9)) : empty);
    if (ema21Ref.current) ema21Ref.current.setData(indicatorVis.ema21 && candles.length > 21 ? toLineData(computeEMA(candles, 21)) : empty);
    if (ema50Ref.current) ema50Ref.current.setData(indicatorVis.ema50 && candles.length > 50 ? toLineData(computeEMA(candles, 50)) : empty);
    if (ema200Ref.current) ema200Ref.current.setData(indicatorVis.ema200 && candles.length > 200 ? toLineData(computeEMA(candles, 200)) : empty);
    if (vwapRef.current) vwapRef.current.setData(indicatorVis.vwap && candles.length > 0 ? toLineData(computeVWAP(candles)) : empty);
  }, [indicatorVis, showIndicators, candles]);

  // Update markers
  useEffect(() => {
    if (!markersRef.current) return;
    const sorted = [...markers].sort((a, b) => a.time - b.time);
    markersRef.current.setMarkers(
      sorted.map((m) => ({ time: m.time as Time, position: m.position, color: m.color, shape: m.shape, text: m.text })) as SeriesMarker<Time>[]
    );
  }, [markers]);

  // Update horizontal lines
  useEffect(() => {
    if (!candleSeriesRef.current) return;
    for (const line of priceLinesRef.current) {
      try { candleSeriesRef.current.removePriceLine(line); } catch { /* ignore */ }
    }
    priceLinesRef.current = [];
    for (const line of horizontalLines) {
      const pl = candleSeriesRef.current.createPriceLine({
        price: line.price, color: line.color, lineWidth: 1,
        lineStyle: line.lineStyle, axisLabelVisible: true, title: line.title,
      });
      priceLinesRef.current.push(pl);
    }
  }, [horizontalLines]);

  // Apply synced visible range from the other chart
  useEffect(() => {
    if (!syncRange || !setRangeSilentlyRef.current) return;
    setRangeSilentlyRef.current(syncRange);
  }, [syncRange]);

  return <div ref={containerRef} className="w-full" />;
});

export default TradingChart;
