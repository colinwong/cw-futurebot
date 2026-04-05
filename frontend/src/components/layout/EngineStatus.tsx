"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { formatTime } from "@/lib/timezone";

export default function EngineStatus() {
  const [lastActivity, setLastActivity] = useState<string>("Engine stopped");
  const [signalCount, setSignalCount] = useState(0);
  const { subscribe } = useWebSocket();

  useEffect(() => {
    const unsubs = [
      subscribe("signal", (data) => {
        const d = data as Record<string, unknown>;
        setSignalCount((c) => c + 1);
        const dir = d.direction as string;
        const sym = d.symbol as string;
        const strategy = d.strategy_name as string;
        const decision = d.decision as Record<string, unknown> | null;
        const action = decision?.action as string || "?";
        setLastActivity(`Signal: ${dir} ${sym} (${strategy}) → ${action} at ${formatTime(Date.now() / 1000)}`);
      }),
      subscribe("system", (data) => {
        const d = data as Record<string, unknown>;
        if (d.event === "engine_started") setLastActivity("Engine started — evaluating strategies...");
        if (d.event === "engine_stopped") setLastActivity("Engine stopped");
        if (d.event === "ib_connected") setLastActivity("IB reconnected");
      }),
    ];
    return () => unsubs.forEach((u) => u());
  }, [subscribe]);

  return (
    <div className="flex items-center justify-between px-4 py-0.5 bg-gray-950 border-b border-gray-800 text-xs text-gray-500">
      <span>{lastActivity}</span>
      {signalCount > 0 && (
        <span>Signals today: {signalCount}</span>
      )}
    </div>
  );
}
