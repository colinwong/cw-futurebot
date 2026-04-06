"use client";

import { useState, useEffect, useRef } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { getStatus } from "@/lib/api";
import { formatTime } from "@/lib/timezone";

export default function EngineStatus() {
  const [lastActivity, setLastActivity] = useState<string>("Loading...");
  const [signalCount, setSignalCount] = useState(0);
  const [evaluating, setEvaluating] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [engineOn, setEngineOn] = useState(false);
  const intervalRef = useRef<number>(30);
  const countdownRef = useRef<ReturnType<typeof setInterval>>(undefined);
  const { subscribe } = useWebSocket();

  // Check engine status on mount
  useEffect(() => {
    getStatus()
      .then((res: Record<string, unknown>) => {
        const running = !!res.engine_running;
        setEngineOn(running);
        setLastActivity(running ? "Engine running — waiting for next evaluation..." : "Engine stopped");
      })
      .catch(() => {});
  }, []);

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
        if (d.event === "engine_started") {
          setEngineOn(true);
          setLastActivity("Engine started — waiting for first evaluation...");
        }
        if (d.event === "engine_stopped") {
          setEngineOn(false);
          setLastActivity("Engine stopped");
          setCountdown(null);
          clearInterval(countdownRef.current);
        }
        if (d.event === "engine_eval_start") {
          setEvaluating(true);
          setCountdown(null);
          clearInterval(countdownRef.current);
          if (d.interval) intervalRef.current = d.interval as number;
          setLastActivity("Evaluating strategies...");
        }
        if (d.event === "engine_eval_done") {
          setEvaluating(false);
          // Start countdown to next evaluation
          let remaining = intervalRef.current;
          setCountdown(remaining);
          clearInterval(countdownRef.current);
          countdownRef.current = setInterval(() => {
            remaining -= 1;
            if (remaining <= 0) {
              clearInterval(countdownRef.current);
              setCountdown(null);
            } else {
              setCountdown(remaining);
            }
          }, 1000);
        }
        if (d.event === "ib_connected") setLastActivity("IB reconnected");
      }),
    ];
    return () => {
      unsubs.forEach((u) => u());
      clearInterval(countdownRef.current);
    };
  }, [subscribe]);

  return (
    <div className="flex items-center justify-between px-4 py-0.5 bg-gray-950 border-b border-gray-800 text-xs">
      <div className="flex items-center gap-2">
        {engineOn && (
          <span className={`w-1.5 h-1.5 rounded-full ${evaluating ? "bg-yellow-400 animate-pulse" : "bg-green-500"}`} />
        )}
        <span className="text-gray-500">{lastActivity}</span>
      </div>
      <div className="flex items-center gap-3 text-gray-600">
        {countdown !== null && (
          <span>Next eval: {countdown}s</span>
        )}
        {signalCount > 0 && (
          <span>Signals: {signalCount}</span>
        )}
      </div>
    </div>
  );
}
