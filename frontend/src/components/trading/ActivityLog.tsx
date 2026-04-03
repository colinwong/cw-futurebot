"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { formatTime } from "@/lib/timezone";

interface LogEntry {
  id: string;
  time: string;
  type: "trade" | "order" | "system";
  typeLabel: string;
  message: string;
  typeColor: string;
  msgColor: string;
}

function formatOrderMessage(d: Record<string, unknown>): string {
  if (d.status === "FILLED") {
    return `Order #${d.ib_order_id} filled @ ${(d.fill_price as number)?.toFixed(2)} x${d.quantity}`;
  }
  if (d.status) return `Order #${d.ib_order_id} ${d.status}`;
  return JSON.stringify(d).slice(0, 60);
}

function formatPositionMessage(d: Record<string, unknown>): string {
  if (d.action === "updated") return "Position updated";
  if (d.direction) return `${d.direction} ${d.symbol} x${d.quantity} @ ${(d.entry_price as number)?.toFixed(2)}`;
  return JSON.stringify(d).slice(0, 60);
}

function formatSystemMessage(d: Record<string, unknown>): string {
  if (d.event_type) return `${d.event_type}: ${JSON.stringify(d.details || "").slice(0, 40)}`;
  return JSON.stringify(d).slice(0, 60);
}

export default function ActivityLog() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const { subscribe } = useWebSocket();

  useEffect(() => {
    function makeEntry(type: LogEntry["type"], typeLabel: string, typeColor: string, message: string): LogEntry {
      return { id: `${Date.now()}-${Math.random()}`, time: formatTime(Date.now() / 1000), type, typeLabel, message, typeColor, msgColor: "text-gray-300" };
    }

    const unsubs = [
      subscribe("order", (data) => {
        const d = data as Record<string, unknown>;
        setEntries((prev) => [makeEntry("order", "ORDER", "bg-blue-900 text-blue-400", formatOrderMessage(d)), ...prev].slice(0, 100));
      }),
      subscribe("position", (data) => {
        const d = data as Record<string, unknown>;
        setEntries((prev) => [makeEntry("trade", "TRADE", "bg-green-900 text-green-400", formatPositionMessage(d)), ...prev].slice(0, 100));
      }),
      subscribe("system", (data) => {
        const d = data as Record<string, unknown>;
        setEntries((prev) => [makeEntry("system", "SYS", "bg-yellow-900 text-yellow-400", formatSystemMessage(d)), ...prev].slice(0, 100));
      }),
    ];
    return () => unsubs.forEach((u) => u());
  }, [subscribe]);

  return (
    <div className="p-3 h-full">
      <div className="text-sm font-bold text-gray-300 mb-2">Activity Log</div>
      {entries.length === 0 ? (
        <div className="text-xs text-gray-600">No activity yet...</div>
      ) : (
        <div className="space-y-1.5">
          {entries.map((e) => (
            <div key={e.id} className="text-xs border-b border-gray-800 pb-1">
              <div className="flex items-center gap-2">
                <span className="text-gray-500 shrink-0">{e.time}</span>
                <span className={`px-1 py-0.5 rounded text-xs ${e.typeColor}`}>
                  {e.typeLabel}
                </span>
                <span className={e.msgColor}>{e.message}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
