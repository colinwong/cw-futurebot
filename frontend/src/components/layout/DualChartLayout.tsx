"use client";

import { useState, useEffect, useMemo } from "react";
import TradingChart from "@/components/chart/TradingChart";
import ChartTimeframe from "@/components/chart/ChartTimeframe";
import { useMarketData } from "@/hooks/useMarketData";
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

// Module-level chart settings — persist across page navigations
const chartSettings: Record<string, { barSize: string; duration: string }> = {};

function SymbolChart({ symbol, positions }: { symbol: Symbol; positions: PositionOverlay[] }) {
  const saved = chartSettings[symbol] || { barSize: "5 mins", duration: "2 D" };
  const [barSize, setBarSize] = useState(saved.barSize);
  const [duration, setDuration] = useState(saved.duration);
  const { candles, lastTick, loading } = useMarketData(symbol, barSize, duration);

  const handleTimeframe = (newBarSize: string, newDuration: string) => {
    setBarSize(newBarSize);
    setDuration(newDuration);
    chartSettings[symbol] = { barSize: newBarSize, duration: newDuration };
  };

  // Generate chart overlays from positions
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
      // Entry marker
      if (pos.entry_price > 0) {
        const entryEpoch = Math.floor(new Date(pos.entry_timestamp).getTime() / 1000) + getTimezoneOffsetSec();
        m.push({
          time: entryEpoch,
          position: pos.direction === "LONG" ? "belowBar" : "aboveBar",
          color: pos.direction === "LONG" ? "#26a69a" : "#ef5350",
          shape: pos.direction === "LONG" ? "arrowUp" : "arrowDown",
          text: `${pos.direction} @ ${pos.entry_price.toFixed(2)}`,
        });

        // Entry price line
        lines.push({
          price: pos.entry_price,
          color: "#4a90d9",
          lineStyle: 2, // dashed
          title: `Entry ${pos.entry_price.toFixed(2)}`,
        });
      }

      // Stop line
      if (pos.stop_price) {
        lines.push({
          price: pos.stop_price,
          color: "#ef5350",
          lineStyle: 2,
          title: `Stop ${pos.stop_price.toFixed(2)}`,
        });
      }

      // Target line
      if (pos.target_price) {
        lines.push({
          price: pos.target_price,
          color: "#26a69a",
          lineStyle: 2,
          title: `Target ${pos.target_price.toFixed(2)}`,
        });
      }
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
        <ChartTimeframe selected={barSize} onSelect={handleTimeframe} />
      </div>
      {loading ? (
        <div className="flex items-center justify-center h-[400px] text-gray-500">
          Loading {symbol} data...
        </div>
      ) : (
        <TradingChart
          candles={candles}
          height={400}
          markers={markers}
          horizontalLines={horizontalLines}
        />
      )}
    </div>
  );
}

export default function DualChartLayout() {
  const [positions, setPositions] = useState<PositionOverlay[]>([]);
  const { subscribe } = useWebSocket();

  useEffect(() => {
    getPositions(true)
      .then((res) => setPositions(res.positions as unknown as PositionOverlay[]))
      .catch(console.error);
  }, []);

  // Refresh positions when they change
  useEffect(() => {
    const unsub = subscribe("position", () => {
      getPositions(true)
        .then((res) => setPositions(res.positions as unknown as PositionOverlay[]))
        .catch(console.error);
    });
    return unsub;
  }, [subscribe]);

  const esPositions = positions.filter((p) => p.symbol === "ES");
  const nqPositions = positions.filter((p) => p.symbol === "NQ");

  return (
    <div className="grid grid-cols-2 gap-2">
      <SymbolChart symbol="ES" positions={esPositions} />
      <SymbolChart symbol="NQ" positions={nqPositions} />
    </div>
  );
}
