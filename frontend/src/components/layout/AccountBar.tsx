"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { getStatus, reconnectIB, startEngine, stopEngine } from "@/lib/api";
import type { AccountInfo } from "@/lib/types";

export default function AccountBar() {
  const { connected: wsConnected, subscribe } = useWebSocket();
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [ibConnected, setIbConnected] = useState(false);
  const [ibAccount, setIbAccount] = useState<string | null>(null);
  const [engineRunning, setEngineRunning] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [togglingEngine, setTogglingEngine] = useState(false);

  const handleToggleEngine = async () => {
    setTogglingEngine(true);
    try {
      if (engineRunning) {
        await stopEngine();
        setEngineRunning(false);
      } else {
        await startEngine();
        setEngineRunning(true);
      }
    } catch { /* ignore */ }
    finally { setTogglingEngine(false); }
  };

  const handleReconnect = async () => {
    setReconnecting(true);
    try {
      const res = await reconnectIB();
      if (res.status === "connected") {
        setIbConnected(true);
      }
    } catch { /* ignore */ }
    finally {
      setReconnecting(false);
    }
  };

  // Poll status endpoint every 10s
  useEffect(() => {
    const fetchStatus = () => {
      getStatus()
        .then((res: Record<string, unknown>) => {
          setIbConnected(res.ib_connected as boolean);
          setIbAccount(res.ib_account as string | null);
          setEngineRunning(!!res.engine_running);
          if (res.account) {
            setAccount(res.account as AccountInfo);
          }
        })
        .catch(() => setIbConnected(false));
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  // Also update account from WebSocket events
  useEffect(() => {
    const unsub = subscribe("account", (data) => {
      setAccount(data as AccountInfo);
    });
    return unsub;
  }, [subscribe]);

  return (
    <div className="flex items-center justify-between px-4 py-2 bg-gray-900 border-b border-gray-800 text-sm">
      <div className="flex items-center gap-6">
        <span className="font-bold text-gray-300">FutureBot</span>
        <div className="flex items-center gap-1">
          <span className="text-gray-500">Balance:</span>
          <span className="font-mono">${account?.balance?.toLocaleString() ?? "—"}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-gray-500">Daily P&L:</span>
          <span
            className={`font-mono ${
              (account?.realized_pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400"
            }`}
          >
            ${account?.realized_pnl?.toFixed(2) ?? "—"}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-gray-500">Unrealized:</span>
          <span
            className={`font-mono ${
              (account?.unrealized_pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400"
            }`}
          >
            ${account?.unrealized_pnl?.toFixed(2) ?? "—"}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-gray-500">Margin:</span>
          <span className="font-mono">${account?.margin_used?.toLocaleString() ?? "—"}</span>
        </div>
      </div>
      <div className="flex items-center gap-4">
        {/* IB Gateway status */}
        <div className="flex items-center gap-1.5">
          <div
            className={`w-2 h-2 rounded-full ${ibConnected ? "bg-green-500" : "bg-red-500"}`}
          />
          <span className="text-gray-500 text-xs">
            IB {ibConnected ? (ibAccount ?? "Connected") : "Disconnected"}
          </span>
          {!ibConnected && (
            <button
              onClick={handleReconnect}
              disabled={reconnecting}
              className="px-1.5 py-0.5 text-xs bg-blue-800 hover:bg-blue-700 text-blue-200 rounded disabled:opacity-50"
            >
              {reconnecting ? "..." : "Reconnect"}
            </button>
          )}
        </div>
        {/* Algo engine start/stop */}
        <button
          onClick={handleToggleEngine}
          disabled={togglingEngine || !ibConnected}
          className={`px-2 py-0.5 text-xs rounded font-bold disabled:opacity-50 disabled:cursor-not-allowed ${
            engineRunning
              ? "bg-red-800 hover:bg-red-700 text-red-200"
              : "bg-green-800 hover:bg-green-700 text-green-200"
          }`}
        >
          {togglingEngine ? "..." : engineRunning ? "Stop Engine" : "Start Engine"}
        </button>
        {/* WebSocket status */}
        <div className="flex items-center gap-1.5">
          <div
            className={`w-2 h-2 rounded-full ${wsConnected ? "bg-green-500" : "bg-red-500"}`}
          />
          <span className="text-gray-500 text-xs">
            WS {wsConnected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>
    </div>
  );
}
