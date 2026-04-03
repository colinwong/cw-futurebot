"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import type { AccountInfo } from "@/lib/types";

export default function AccountBar() {
  const { connected, subscribe } = useWebSocket();
  const [account, setAccount] = useState<AccountInfo | null>(null);

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
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${connected ? "bg-green-500" : "bg-red-500"}`}
        />
        <span className="text-gray-500 text-xs">{connected ? "Connected" : "Disconnected"}</span>
      </div>
    </div>
  );
}
