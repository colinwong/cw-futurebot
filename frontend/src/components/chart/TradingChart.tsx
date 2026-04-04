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
import { formatDate } from "@/lib/timezone";

// RTH hours in ET: 9:30 AM - 4:00 PM
const RTH_START_HOUR = 9;
const RTH_START_MIN = 30;
const RTH_END_HOUR = 16;
const RTH_END_MIN = 0;

function isRTH(localEpoch: number): boolean {
  // localEpoch is already shifted to display timezone by useMarketData
  // We need to check ET hours — but the shift was to the configured display TZ
  // For RTH we always check ET, so we need to compute ET time from the shifted epoch
  // Since the epoch was shifted by display TZ offset, we need to undo that and apply ET offset
  // Simpler: just check the UTC hours of the raw epoch
  // Actually, the localEpoch has already been adjusted — the UTC hours of this value
  // represent the display timezone's local time
  const d = new Date(localEpoch * 1000);
  const h = d.getUTCHours();
  const m = d.getUTCMinutes();
  const totalMin = h * 60 + m;
  const rthStart = RTH_START_HOUR * 60 + RTH_START_MIN; // 570
  const rthEnd = RTH_END_HOUR * 60 + RTH_END_MIN; // 960
  return totalMin >= rthStart && totalMin < rthEnd;
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
}

export default function TradingChart({
  candles,
  height = 400,
  markers = [],
  horizontalLines = [],
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const markersRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const priceLinesRef = useRef<any[]>([]);

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
          if (h === 0 && m === 0) {
            return formatDate(time);
          }
          return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
        },
      },
      height,
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

    // Create markers plugin
    markersRef.current = createSeriesMarkers(candleSeries, []);

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
      markersRef.current = null;
      priceLinesRef.current = [];
      initialLoadDone.current = false;
      prevLengthRef.current = 0;
    };
  }, [height]);

  // Set candle + volume + RTH data
  const prevLengthRef = useRef(0);
  const initialLoadDone = useRef(false);
  const prevFirstTime = useRef<number>(0);
  useEffect(() => {
    if (!candleSeriesRef.current || !chartRef.current || !volumeSeriesRef.current || candles.length === 0) return;

    // Detect timeframe change — if first candle time changed, force full reload
    const firstTime = candles[0].time;
    if (firstTime !== prevFirstTime.current) {
      initialLoadDone.current = false;
      prevLengthRef.current = 0;
      prevFirstTime.current = firstTime;
    }

    // RTH candles get full colors, non-RTH get dimmer colors
    const candleData: CandlestickData<Time>[] = candles.map((c) => {
      const rth = isRTH(c.time);
      const up = c.close >= c.open;
      return {
        time: c.time as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        // Non-RTH candles are dimmer
        color: rth
          ? (up ? "#26a69a" : "#ef5350")
          : (up ? "#1a6e66" : "#8a3030"),
        wickColor: rth
          ? (up ? "#26a69a" : "#ef5350")
          : (up ? "#1a6e66" : "#8a3030"),
        borderColor: rth
          ? (up ? "#26a69a" : "#ef5350")
          : (up ? "#1a6e66" : "#8a3030"),
      };
    });

    const volumeData: HistogramData<Time>[] = candles.map((c) => ({
      time: c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? "rgba(38, 166, 154, 0.3)" : "rgba(239, 83, 80, 0.3)",
    }));

    if (!initialLoadDone.current || candles.length < prevLengthRef.current) {
      candleSeriesRef.current.setData(candleData);
      volumeSeriesRef.current.setData(volumeData);

      chartRef.current.timeScale().fitContent();
      initialLoadDone.current = true;
    } else {
      const last = candles[candles.length - 1];
      const rth = isRTH(last.time);
      const up = last.close >= last.open;
      candleSeriesRef.current.update({
        time: last.time as Time,
        open: last.open,
        high: last.high,
        low: last.low,
        close: last.close,
        color: rth ? (up ? "#26a69a" : "#ef5350") : (up ? "#1a6e66" : "#8a3030"),
        wickColor: rth ? (up ? "#26a69a" : "#ef5350") : (up ? "#1a6e66" : "#8a3030"),
        borderColor: rth ? (up ? "#26a69a" : "#ef5350") : (up ? "#1a6e66" : "#8a3030"),
      });
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

  return <div ref={containerRef} className="w-full" />;
}
