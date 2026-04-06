"use client";

import { useState, useEffect, useRef } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { getStatus } from "@/lib/api";
import { formatTime } from "@/lib/timezone";

interface StrategyEval {
  strategy: string;
  symbol: string;
  timestamp: string;
  price: number;
  has_signal: boolean;
  direction: string | null;
  reasoning: string;
}

// Short strategy names for display
const STRATEGY_SHORT: Record<string, string> = {
  vwap_trend_continuation: "VWAP",
  bollinger_mean_reversion: "BB",
  orb_momentum: "ORB",
};

export default function EngineStatus() {
  const [lastActivity, setLastActivity] = useState<string>("Loading...");
  const [signalCount, setSignalCount] = useState(0);
  const [evaluating, setEvaluating] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [engineOn, setEngineOn] = useState(false);
  const [lastEvals, setLastEvals] = useState<Record<string, StrategyEval>>({});
  const intervalRef = useRef<number>(30);
  const countdownRef = useRef<ReturnType<typeof setInterval>>(undefined);
  const { subscribe } = useWebSocket();

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
      subscribe("strategy_eval", (data) => {
        const d = data as StrategyEval;
        setLastEvals((prev) => ({ ...prev, [`${d.strategy}|${d.symbol}`]: d }));
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
        }
        if (d.event === "engine_eval_done") {
          setEvaluating(false);
          setLastActivity(`Last eval: ${formatTime(Date.now() / 1000)}`);
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

  // Group evals by symbol for display
  const evalEntries = Object.values(lastEvals);

  return (
    <div className="px-4 py-0.5 bg-gray-950 border-b border-gray-800 text-xs">
      {/* Top line: engine status + countdown */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {engineOn && (
            <span className={`w-1.5 h-1.5 rounded-full ${evaluating ? "bg-yellow-400 animate-pulse" : "bg-green-500"}`} />
          )}
          <span className="text-gray-500">{lastActivity}</span>
        </div>
        <div className="flex items-center gap-3 text-gray-600">
          {countdown !== null && <span>Next eval: {countdown}s</span>}
          {signalCount > 0 && <span>Signals: {signalCount}</span>}
        </div>
      </div>

      {/* Pinned last eval results per strategy */}
      {evalEntries.length > 0 && (
        <div className="flex items-center gap-3 mt-0.5 text-gray-600">
          {evalEntries.map((e) => {
            const shortName = STRATEGY_SHORT[e.strategy] || e.strategy;
            return (
              <span key={`${e.strategy}|${e.symbol}`} className="flex items-center gap-1">
                <span className="text-gray-500">{shortName}/{e.symbol}:</span>
                {e.has_signal ? (
                  <span className={e.direction === "LONG" ? "text-green-400" : "text-red-400"}>
                    {e.direction}
                  </span>
                ) : (
                  <span className="text-gray-600">—</span>
                )}
                <span className="text-gray-700">{formatTime(e.timestamp)}</span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
