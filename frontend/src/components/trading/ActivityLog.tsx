"use client";

import { useState, useEffect, useRef } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { getLogs } from "@/lib/api";
import { formatTime, formatDateTime } from "@/lib/timezone";
import { formatEventData, cleanJsonString } from "@/lib/formatEvent";

interface LogEntry {
  id: string;
  shortTime: string;
  fullTime: string;
  type: "trade" | "order" | "system";
  typeLabel: string;
  message: string;
  typeColor: string;
}

const TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  order: { label: "ORDER", color: "bg-blue-900 text-blue-400" },
  fill: { label: "FILL", color: "bg-cyan-900 text-cyan-400" },
  trade: { label: "TRADE", color: "bg-green-900 text-green-400" },
  system: { label: "SYS", color: "bg-yellow-900 text-yellow-400" },
};

function shortTimeStr(ts: string | number): string {
  const date = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts);
  return date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

export default function ActivityLog() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const { subscribe } = useWebSocket();
  const historicalLoaded = useRef(false);

  useEffect(() => {
    if (historicalLoaded.current) return;
    const clearedAt = localStorage.getItem("futurebot_clear_activity") || "";
    getLogs(30)
      .then((res) => {
        const historical: LogEntry[] = res.entries
          .filter((e) => e.type !== "news")
          .filter((e) => !clearedAt || e.timestamp > clearedAt)
          .map((e, i) => {
            const cfg = TYPE_CONFIG[e.type] || TYPE_CONFIG.system;
            return {
              id: `hist-${i}`,
              shortTime: shortTimeStr(e.timestamp),
              fullTime: formatDateTime(e.timestamp),
              type: (e.type === "fill" ? "order" : e.type) as LogEntry["type"],
              typeLabel: cfg.label,
              message: e.message,
              typeColor: cfg.color,
            };
          });
        setEntries(historical);
        historicalLoaded.current = true;
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    function makeEntry(type: LogEntry["type"], typeLabel: string, typeColor: string, message: string): LogEntry {
      const now = Date.now() / 1000;
      return {
        id: `live-${Date.now()}-${Math.random()}`,
        shortTime: shortTimeStr(now),
        fullTime: formatTime(now),
        type, typeLabel, message, typeColor,
      };
    }

    const unsubs = [
      subscribe("order", (data) => {
        const d = data as Record<string, unknown>;
        setEntries((prev) => [makeEntry("order", "ORDER", "bg-blue-900 text-blue-400", formatEventData(d)), ...prev].slice(0, 100));
      }),
      subscribe("position", (data) => {
        const d = data as Record<string, unknown>;
        setEntries((prev) => [makeEntry("trade", "TRADE", "bg-green-900 text-green-400", formatEventData(d)), ...prev].slice(0, 100));
      }),
      subscribe("system", (data) => {
        const d = data as Record<string, unknown>;
        if (d.event === "engine_eval_start" || d.event === "engine_eval_done") return;
        setEntries((prev) => [makeEntry("system", "SYS", "bg-yellow-900 text-yellow-400", formatEventData(d)), ...prev].slice(0, 100));
      }),
    ];
    return () => unsubs.forEach((u) => u());
  }, [subscribe]);

  const handleClear = () => {
    setEntries([]);
    const ts = new Date().toISOString();
    try { localStorage.setItem("futurebot_clear_activity", ts); } catch {}
  };

  return (
    <div className="p-3 h-full">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-bold text-gray-300">Activity Log</span>
        {entries.length > 0 && (
          <button onClick={handleClear} className="text-xs text-gray-600 hover:text-gray-400">Clear</button>
        )}
      </div>
      {entries.length === 0 ? (
        <div className="text-xs text-gray-600">No activity yet...</div>
      ) : (
        <div className="space-y-0.5">
          {entries.map((e) => (
            <div
              key={e.id}
              className="text-xs border-b border-gray-800 pb-0.5 cursor-pointer hover:bg-gray-900/50"
              onClick={() => setExpanded(expanded === e.id ? null : e.id)}
            >
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-gray-600 shrink-0 w-16 text-right">{e.shortTime}</span>
                <span className={`px-1 py-0.5 rounded shrink-0 ${e.typeColor}`}>{e.typeLabel}</span>
                <span className="text-gray-300 truncate">{cleanJsonString(e.message)}</span>
              </div>
              {expanded === e.id && (
                <div className="mt-1 ml-[70px] text-gray-500 text-[10px] space-y-0.5 pb-1">
                  <div>{e.fullTime}</div>
                  <div className="break-all">{e.message}</div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
