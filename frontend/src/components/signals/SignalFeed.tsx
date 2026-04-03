"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { formatTime } from "@/lib/timezone";
import type { SignalRecord } from "@/lib/types";

export default function SignalFeed() {
  const [signals, setSignals] = useState<SignalRecord[]>([]);
  const { subscribe } = useWebSocket();

  useEffect(() => {
    const unsub = subscribe("signal", (data) => {
      const signal = data as SignalRecord;
      setSignals((prev) => [signal, ...prev].slice(0, 50));
    });
    return unsub;
  }, [subscribe]);

  return (
    <div className="p-3 h-full">
      <div className="text-sm font-bold text-gray-300 mb-2">Signal Feed</div>
      {signals.length === 0 ? (
        <div className="text-xs text-gray-600">Waiting for signals...</div>
      ) : (
        <div className="space-y-2">
          {signals.map((sig) => (
            <div key={sig.id} className="text-xs border-b border-gray-800 pb-1.5">
              <div className="flex items-center gap-2">
                <span className="text-gray-500">
                  {formatTime(sig.timestamp)}
                </span>
                <span
                  className={`font-bold ${
                    sig.direction === "LONG" ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {sig.direction} {sig.symbol}
                </span>
                <span className="text-gray-500">({sig.strategy_name})</span>
              </div>
              {sig.decision && (
                <div
                  className={`mt-0.5 ${
                    sig.decision.action === "EXECUTE"
                      ? "text-green-500"
                      : "text-orange-400"
                  }`}
                >
                  → {sig.decision.action}: {sig.decision.reasoning.slice(0, 100)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
