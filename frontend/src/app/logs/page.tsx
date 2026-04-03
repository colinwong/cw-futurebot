"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { formatTime } from "@/lib/timezone";

interface LogEntry {
  id: string;
  time: string;
  type: "trade" | "order" | "system" | "news";
  typeLabel: string;
  message: string;
  typeColor: string;
}

function formatOrderMsg(d: Record<string, unknown>): string {
  if (d.status === "FILLED") return `Order #${d.ib_order_id} filled @ ${(d.fill_price as number)?.toFixed(2)} x${d.quantity}`;
  if (d.status) return `Order #${d.ib_order_id} ${d.status}`;
  return JSON.stringify(d).slice(0, 80);
}

function formatPositionMsg(d: Record<string, unknown>): string {
  if (d.action === "updated") return "Position updated";
  if (d.direction) return `${d.direction} ${d.symbol} x${d.quantity} @ ${(d.entry_price as number)?.toFixed(2)}`;
  return JSON.stringify(d).slice(0, 80);
}

function formatSystemMsg(d: Record<string, unknown>): string {
  if (d.event_type) return `${d.event_type}: ${JSON.stringify(d.details || "").slice(0, 60)}`;
  return JSON.stringify(d).slice(0, 80);
}

function formatNewsMsg(d: Record<string, unknown>): string {
  return `[${d.impact_rating}] ${d.headline}`;
}

const TYPE_CONFIG = {
  order: { label: "ORDER", color: "bg-blue-900 text-blue-400" },
  trade: { label: "TRADE", color: "bg-green-900 text-green-400" },
  system: { label: "SYS", color: "bg-yellow-900 text-yellow-400" },
  news: { label: "NEWS", color: "bg-purple-900 text-purple-400" },
};

type FilterType = "all" | "trade" | "order" | "system" | "news";

export default function LogsPage() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState<FilterType>("all");
  const { subscribe } = useWebSocket();

  useEffect(() => {
    const addEntry = (type: LogEntry["type"], formatter: (d: Record<string, unknown>) => string) => (data: unknown) => {
      const d = data as Record<string, unknown>;
      const cfg = TYPE_CONFIG[type];
      const entry: LogEntry = {
        id: `${Date.now()}-${Math.random()}`,
        time: formatTime(Date.now() / 1000),
        type,
        typeLabel: cfg.label,
        message: formatter(d),
        typeColor: cfg.color,
      };
      setEntries((prev) => [entry, ...prev].slice(0, 500));
    };

    const unsubs = [
      subscribe("order", addEntry("order", formatOrderMsg)),
      subscribe("position", addEntry("trade", formatPositionMsg)),
      subscribe("system", addEntry("system", formatSystemMsg)),
      subscribe("news", addEntry("news", formatNewsMsg)),
    ];
    return () => unsubs.forEach((u) => u());
  }, [subscribe]);

  const filtered = filter === "all" ? entries : entries.filter((e) => e.type === filter);

  const counts = {
    all: entries.length,
    trade: entries.filter((e) => e.type === "trade").length,
    order: entries.filter((e) => e.type === "order").length,
    system: entries.filter((e) => e.type === "system").length,
    news: entries.filter((e) => e.type === "news").length,
  };

  return (
    <div className="p-4 flex flex-col h-[calc(100vh-30px)]">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-bold">Activity Log</h1>
        <div className="flex gap-1.5">
          {(["all", "trade", "order", "system", "news"] as FilterType[]).map((f) => (
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
        {filtered.length === 0 ? (
          <div className="text-xs text-gray-600">No activity yet... Events will appear here as trades, orders, news, and system events occur.</div>
        ) : (
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-[#0f1117]">
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left py-1 w-40">Time</th>
                <th className="text-left w-20">Type</th>
                <th className="text-left">Message</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e) => (
                <tr key={e.id} className="border-b border-gray-800">
                  <td className="py-1.5 text-gray-500">{e.time}</td>
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
