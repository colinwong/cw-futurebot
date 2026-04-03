"use client";

import { useState } from "react";
import TradingChart from "@/components/chart/TradingChart";
import ChartTimeframe from "@/components/chart/ChartTimeframe";
import { useMarketData } from "@/hooks/useMarketData";
import type { Symbol } from "@/lib/types";

function SymbolChart({ symbol }: { symbol: Symbol }) {
  const [barSize, setBarSize] = useState("5 mins");
  const [duration, setDuration] = useState("2 D");
  const { candles, lastTick, loading } = useMarketData(symbol, barSize, duration);

  const handleTimeframe = (newBarSize: string, newDuration: string) => {
    setBarSize(newBarSize);
    setDuration(newDuration);
  };

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
        <TradingChart candles={candles} height={400} />
      )}
    </div>
  );
}

export default function DualChartLayout() {
  return (
    <div className="grid grid-cols-2 gap-2">
      <SymbolChart symbol="ES" />
      <SymbolChart symbol="NQ" />
    </div>
  );
}
