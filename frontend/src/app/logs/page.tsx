"use client";

import { useState, useEffect, useRef } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { getLogs } from "@/lib/api";
import { formatDateTime } from "@/lib/timezone";

interface LogEntry {
  id: string;
  timestamp: string;
  type: "trade" | "order" | "fill" | "system" | "news";
  typeLabel: string;
  message: string;
  typeColor: string;
}

const TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  order: { label: "ORDER", color: "bg-blue-900 text-blue-400" },
  fill: { label: "FILL", color: "bg-cyan-900 text-cyan-400" },
  trade: { label: "TRADE", color: "bg-green-900 text-green-400" },
  system: { label: "SYS", color: "bg-yellow-900 text-yellow-400" },
  news: { label: "NEWS", color: "bg-purple-900 text-purple-400" },
};

type FilterType = "all" | "trade" | "order" | "fill" | "system" | "news";

function formatLiveOrderMsg(d: Record<string, unknown>): string {
  if (d.status === "FILLED") return `Order #${d.ib_order_id} filled @ ${(d.fill_price as number)?.toFixed(2)} x${d.quantity}`;
  if (d.status) return `Order #${d.ib_order_id} ${d.status}`;
  return JSON.stringify(d).slice(0, 80);
}

function formatLivePositionMsg(d: Record<string, unknown>): string {
  if (d.action === "updated") return "Position updated";
  if (d.direction) return `${d.direction} ${d.symbol} x${d.quantity} @ ${(d.entry_price as number)?.toFixed(2)}`;
  return JSON.stringify(d).slice(0, 80);
}

function formatLiveNewsMsg(d: Record<string, unknown>): string {
  return `[${d.impact_rating}] [${d.sentiment}] ${d.headline}`;
}

export default function LogsPage() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterType>("all");
  const { subscribe } = useWebSocket();
  const historicalLoaded = useRef(false);

  // Load historical logs from DB on mount
  useEffect(() => {
    getLogs(300)
      .then((res) => {
        const historical: LogEntry[] = res.entries.map((e, i) => {
          const cfg = TYPE_CONFIG[e.type] || TYPE_CONFIG.system;
          return {
            id: `hist-${i}`,
            timestamp: e.timestamp,
            type: e.type as LogEntry["type"],
            typeLabel: cfg.label,
            message: e.message,
            typeColor: cfg.color,
          };
        });
        setEntries(historical);
        historicalLoaded.current = true;
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  // Subscribe to live events and prepend
  useEffect(() => {
    function addLive(type: LogEntry["type"], message: string) {
      const cfg = TYPE_CONFIG[type];
      const entry: LogEntry = {
        id: `live-${Date.now()}-${Math.random()}`,
        timestamp: new Date().toISOString(),
        type,
        typeLabel: cfg.label,
        message,
        typeColor: cfg.color,
      };
      setEntries((prev) => [entry, ...prev].slice(0, 500));
    }

    const unsubs = [
      subscribe("order", (data) => {
        const d = data as Record<string, unknown>;
        addLive("order", formatLiveOrderMsg(d));
      }),
      subscribe("position", (data) => {
        const d = data as Record<string, unknown>;
        addLive("trade", formatLivePositionMsg(d));
      }),
      subscribe("news", (data) => {
        const d = data as Record<string, unknown>;
        addLive("news", formatLiveNewsMsg(d));
      }),
      subscribe("system", (data) => {
        const d = data as Record<string, unknown>;
        addLive("system", JSON.stringify(d).slice(0, 80));
      }),
    ];
    return () => unsubs.forEach((u) => u());
  }, [subscribe]);

  const filtered = filter === "all" ? entries : entries.filter((e) => e.type === filter);

  const counts: Record<FilterType, number> = {
    all: entries.length,
    trade: entries.filter((e) => e.type === "trade").length,
    order: entries.filter((e) => e.type === "order").length,
    fill: entries.filter((e) => e.type === "fill").length,
    system: entries.filter((e) => e.type === "system").length,
    news: entries.filter((e) => e.type === "news").length,
  };

  return (
    <div className="p-4 flex flex-col h-[calc(100vh-30px)]">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-bold">Activity Log</h1>
        <div className="flex gap-1.5">
          {(["all", "order", "fill", "trade", "system", "news"] as FilterType[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 text-xs rounded ${
                filter === f
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {f === "all" ? "All" : TYPE_CONFIG[f].label} ({counts[f]})
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0">
        {loading ? (
          <div className="text-xs text-gray-500">Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="text-xs text-gray-600">No activity yet...</div>
        ) : (
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-[#0f1117]">
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left py-1 w-44">Time</th>
                <th className="text-left w-16">Type</th>
                <th className="text-left">Message</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => (
                <tr key={e.id} className="border-b border-gray-800">
                  <td className="py-1.5 text-gray-500">{formatDateTime(e.timestamp)}</td>
                  <td>
                    <span className={`px-1 py-0.5 rounded ${e.typeColor}`}>
                      {e.typeLabel}
                    </span>
                  </td>
                  <td className="text-gray-300">{e.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
