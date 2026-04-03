"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useOrders } from "@/hooks/useOrders";
import { getPositions } from "@/lib/api";
import type { Position } from "@/lib/types";

export default function PositionStrip() {
  const [positions, setPositions] = useState<Position[]>([]);
  const { subscribe } = useWebSocket();
  const { closePosition, loading } = useOrders();

  // Fetch initial positions
  useEffect(() => {
    getPositions(true)
      .then((res) => setPositions(res.positions as unknown as Position[]))
      .catch(console.error);
  }, []);

  // Subscribe to position updates
  useEffect(() => {
    const unsub = subscribe("position", () => {
      getPositions(true)
        .then((res) => setPositions(res.positions as unknown as Position[]))
        .catch(console.error);
    });
    return unsub;
  }, [subscribe]);

  if (positions.length === 0) return null;

  return (
    <div className="border-t border-gray-800 bg-gray-900 px-4 py-2">
      <div className="text-xs text-gray-500 mb-1">Open Positions</div>
      <div className="flex flex-col gap-1">
        {positions.map((pos) => (
          <div key={pos.id} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-3">
              <span
                className={`font-bold ${
                  pos.direction === "LONG" ? "text-green-400" : "text-red-400"
                }`}
              >
                {pos.direction} {pos.symbol}
              </span>
              <span className="text-gray-400">
                {pos.quantity} @ {pos.entry_price.toFixed(2)}
              </span>
              {pos.protective_order && (
                <span className="text-xs text-gray-600">
                  [Protected: {pos.protective_order.status}]
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
