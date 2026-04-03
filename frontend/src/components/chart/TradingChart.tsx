"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  type IChartApi,
  type ISeriesApi,
  ColorType,
  type CandlestickData,
  type Time,
  type SeriesMarker,
} from "lightweight-charts";
import type { Candle } from "@/lib/types";

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
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const markersRef = useRef<any>(null);

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
      },
      height,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

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
      markersRef.current = null;
      initialLoadDone.current = false;
      prevLengthRef.current = 0;
    };
  }, [height]);

  // Set initial data or update last candle efficiently
  const prevLengthRef = useRef(0);
  const initialLoadDone = useRef(false);
  useEffect(() => {
    if (!candleSeriesRef.current || !chartRef.current || candles.length === 0) return;

    if (!initialLoadDone.current || candles.length < prevLengthRef.current) {
      // Full data load (initial or timeframe change)
      const data: CandlestickData<Time>[] = candles.map((c) => ({
        time: c.time as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));
      candleSeriesRef.current.setData(data);
      // Show all historical data, scrolled to the right
      chartRef.current.timeScale().fitContent();
      initialLoadDone.current = true;
    } else {
      // Incremental update — just update the last candle
      const last = candles[candles.length - 1];
      candleSeriesRef.current.update({
        time: last.time as Time,
        open: last.open,
        high: last.high,
        low: last.low,
        close: last.close,
      });
      // Keep the chart scrolled to show the latest candle without resetting zoom
      chartRef.current.timeScale().scrollToRealTime();
    }
    prevLengthRef.current = candles.length;
  }, [candles]);

  // Update markers (entry/exit arrows, signal diamonds)
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

  // Update horizontal lines (stop/target)
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    horizontalLines.forEach((line) => {
      candleSeriesRef.current!.createPriceLine({
        price: line.price,
        color: line.color,
        lineWidth: 1,
        lineStyle: line.lineStyle,
        axisLabelVisible: true,
        title: line.title,
      });
    });
  }, [horizontalLines]);

  return <div ref={containerRef} className="w-full" />;
}
