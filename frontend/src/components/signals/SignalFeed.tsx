"use client";

import { useState, useEffect, useRef } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { getSignals } from "@/lib/api";
import { formatTime } from "@/lib/timezone";
import type { SignalRecord } from "@/lib/types";

export default function SignalFeed() {
  const [signals, setSignals] = useState<SignalRecord[]>([]);
  const { subscribe } = useWebSocket();
  const historicalLoaded = useRef(false);

  // Load recent signals from DB on mount + poll every 10s
  const fetchSignals = () => {
    const clearedAt = localStorage.getItem("futurebot_clear_signals") || "";
    getSignals({ limit: 30 })
      .then((res) => {
        const filtered = (res.signals as unknown as SignalRecord[])
          .filter((s) => !clearedAt || s.timestamp > clearedAt);
        setSignals(filtered);
        historicalLoaded.current = true;
      })
      .catch(console.error);
  };

  useEffect(() => {
    fetchSignals();
    const interval = setInterval(fetchSignals, 10000);
    return () => clearInterval(interval);
  }, []);

  // Live signals via WebSocket
  const clearedAtRef = useRef(typeof window !== "undefined" ? localStorage.getItem("futurebot_clear_signals") || "" : "");
  useEffect(() => {
    const unsub = subscribe("signal", (data) => {
      const signal = data as SignalRecord;
      if (clearedAtRef.current && signal.timestamp <= clearedAtRef.current) return;
      setSignals((prev) => [signal, ...prev].slice(0, 50));
    });
    return unsub;
  }, [subscribe]);

  const handleClear = () => {
    setSignals([]);
    const ts = new Date().toISOString();
    clearedAtRef.current = ts;
    try { localStorage.setItem("futurebot_clear_signals", ts); } catch {}
  };

  return (
    <div className="p-3 h-full">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-bold text-gray-300">Signal Feed</span>
        {signals.length > 0 && (
          <button onClick={handleClear} className="text-xs text-gray-600 hover:text-gray-400">Clear</button>
        )}
      </div>
      {signals.length === 0 ? (
        <div className="text-xs text-gray-600">No signals</div>
      ) : (
        <div className="space-y-2">
          {signals.map((sig, idx) => (
            <div key={sig.id || `sig-${idx}`} className="text-xs border-b border-gray-800 pb-1.5">
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
