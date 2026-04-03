"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { formatTime } from "@/lib/timezone";

interface LogEntry {
  id: string;
  time: string;
  type: "trade" | "order" | "system";
  message: string;
  color: string;
}

export default function ActivityLog() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const { subscribe } = useWebSocket();

  useEffect(() => {
    const addEntry = (type: LogEntry["type"], color: string) => (data: unknown) => {
      const d = data as Record<string, unknown>;
      const entry: LogEntry = {
        id: `${Date.now()}-${Math.random()}`,
        time: formatTime(Date.now() / 1000),
        type,
        message: d.message as string || JSON.stringify(d).slice(0, 80),
        color,
      };
      setEntries((prev) => [entry, ...prev].slice(0, 100));
    };

    const unsubs = [
      subscribe("order", addEntry("order", "text-blue-400")),
      subscribe("position", addEntry("trade", "text-green-400")),
      subscribe("system", addEntry("system", "text-yellow-400")),
    ];
    return () => unsubs.forEach((u) => u());
  }, [subscribe]);

  return (
    <div className="p-2 h-full">
      <div className="text-sm font-bold text-gray-300 mb-1">Activity Log</div>
      {entries.length === 0 ? (
        <div className="text-xs text-gray-600">No activity yet...</div>
      ) : (
        <div className="space-y-0.5">
          {entries.map((e) => (
            <div key={e.id} className="text-xs flex gap-1.5">
              <span className="text-gray-600 shrink-0">{e.time}</span>
              <span className={e.color}>{e.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
