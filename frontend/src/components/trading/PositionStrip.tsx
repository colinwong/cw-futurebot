"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useOrders } from "@/hooks/useOrders";
import { getPositions } from "@/lib/api";
import { formatTime } from "@/lib/timezone";

interface PositionData {
  id: number;
  symbol: string;
  direction: string;
  quantity: number;
  entry_price: number;
  stop_price: number | null;
  target_price: number | null;
  entry_timestamp: string;
  is_open: boolean;
  protective_status: string | null;
}

export default function PositionStrip() {
  const [positions, setPositions] = useState<PositionData[]>([]);
  const { subscribe } = useWebSocket();
  const { closePosition, loading } = useOrders();

  const fetchPositions = () => {
    getPositions(true)
      .then((res) => setPositions(res.positions as unknown as PositionData[]))
      .catch(console.error);
  };

  useEffect(() => { fetchPositions(); }, []);

  useEffect(() => {
    const unsub = subscribe("position", fetchPositions);
    return unsub;
  }, [subscribe]);

  if (positions.length === 0) return null;

  return (
    <div className="border-t border-gray-800 bg-gray-900 px-4 py-2">
      <div className="text-xs text-gray-500 mb-1">Open Positions</div>
      <div className="flex flex-col gap-1.5">
        {positions.map((pos) => (
          <div key={pos.id} className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-3">
              <span
                className={`font-bold ${
                  pos.direction === "LONG" ? "text-green-400" : "text-red-400"
                }`}
              >
                {pos.direction} {pos.symbol} x{pos.quantity}
              </span>
              <span className="text-gray-300">
                Entry: {pos.entry_price > 0 ? pos.entry_price.toFixed(2) : "MKT (pending fill)"}
              </span>
              {pos.stop_price && (
                <span className="text-red-400">
                  Stop: {pos.stop_price.toFixed(2)}
                </span>
              )}
              {pos.target_price && (
                <span className="text-green-400">
                  Target: {pos.target_price.toFixed(2)}
                </span>
              )}
              <span className="text-gray-600">
                {formatTime(pos.entry_timestamp)}
              </span>
              {pos.protective_status && (
                <span className="text-gray-600">
                  [{pos.protective_status}]
                </span>
              )}
            </div>
            <button
              onClick={() => closePosition(pos.symbol)}
              disabled={loading}
              className="px-2 py-0.5 text-xs bg-red-900 hover:bg-red-800 text-red-300 rounded"
            >
              Close
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
