"use client";

import { useState, useEffect } from "react";
import { getSignals } from "@/lib/api";
import { formatDateTime } from "@/lib/timezone";
import type { SignalRecord } from "@/lib/types";

export default function SignalsPage() {
  const [signals, setSignals] = useState<SignalRecord[]>([]);
  const [filter, setFilter] = useState<{ symbol?: string; action?: string }>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getSignals({ ...filter, limit: 100 })
      .then((res) => setSignals(res.signals as unknown as SignalRecord[]))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [filter]);

  const executed = signals.filter((s) => s.decision?.action === "EXECUTE").length;
  const rejected = signals.filter((s) => s.decision?.action === "REJECT").length;

  return (
    <div className="p-4">
      <h1 className="text-lg font-bold mb-4">Signal Log</h1>

      {/* Stats */}
      <div className="flex gap-4 mb-4 text-xs">
        <div className="bg-gray-900 px-3 py-1.5 rounded">
          Total: <span className="font-bold">{signals.length}</span>
        </div>
        <div className="bg-gray-900 px-3 py-1.5 rounded">
          Executed: <span className="font-bold text-green-400">{executed}</span>
        </div>
        <div className="bg-gray-900 px-3 py-1.5 rounded">
          Rejected: <span className="font-bold text-orange-400">{rejected}</span>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-4">
        <select
          onChange={(e) => setFilter((f) => ({ ...f, symbol: e.target.value || undefined }))}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs"
        >
          <option value="">All Symbols</option>
          <option value="ES">ES</option>
          <option value="NQ">NQ</option>
        </select>
        <select
          onChange={(e) => setFilter((f) => ({ ...f, action: e.target.value || undefined }))}
          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs"
        >
          <option value="">All Actions</option>
          <option value="EXECUTE">Executed</option>
          <option value="REJECT">Rejected</option>
        </select>
      </div>

      {/* Signal list */}
      {loading ? (
        <div className="text-gray-500">Loading...</div>
      ) : (
        <div className="space-y-2">
          {signals.map((sig) => (
            <div key={sig.id} className="bg-gray-900 rounded p-3 text-xs">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">
                    {formatDateTime(sig.timestamp)}
                  </span>
                  <span
                    className={`font-bold ${
                      sig.direction === "LONG" ? "text-green-400" : "text-red-400"
                    }`}
                  >
                    {sig.direction} {sig.symbol}
                  </span>
                  <span className="text-gray-500">{sig.strategy_name}</span>
                  <span className="text-gray-600">
                    strength: {sig.strength.toFixed(2)}
                  </span>
                </div>
                {sig.decision && (
                  <span
                    className={`px-2 py-0.5 rounded ${
                      sig.decision.action === "EXECUTE"
                        ? "bg-green-900 text-green-400"
                        : "bg-orange-900 text-orange-400"
                    }`}
                  >
                    {sig.decision.action}
                  </span>
                )}
              </div>
              {sig.decision && (
                <div className="text-gray-500 mt-1">{sig.decision.reasoning}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
