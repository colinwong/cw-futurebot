"use client";

import { useState, useEffect } from "react";
import { getTrades, getTradeAudit } from "@/lib/api";
import type { TradeRecord } from "@/lib/types";

export default function TradesPage() {
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [audit, setAudit] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getTrades({ limit: 100 })
      .then((res) => setTrades(res.trades as unknown as TradeRecord[]))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSelect = async (tradeId: number) => {
    setSelectedId(tradeId);
    try {
      const data = await getTradeAudit(tradeId);
      setAudit(data);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="p-4">
      <h1 className="text-lg font-bold mb-4">Trade History</h1>

      <div className="grid grid-cols-2 gap-4">
        {/* Trade list */}
        <div>
          {loading ? (
            <div className="text-gray-500">Loading...</div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="text-left py-1">Time</th>
                  <th className="text-left">Symbol</th>
                  <th className="text-left">Direction</th>
                  <th className="text-right">Entry</th>
                  <th className="text-right">Exit</th>
                  <th className="text-right">P&L</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => (
                  <tr
                    key={trade.id}
                    onClick={() => handleSelect(trade.id)}
                    className={`cursor-pointer border-b border-gray-800 hover:bg-gray-900 ${
                      selectedId === trade.id ? "bg-gray-900" : ""
                    }`}
                  >
                    <td className="py-1 text-gray-500">
                      {trade.exit_timestamp
                        ? new Date(trade.exit_timestamp).toLocaleString()
                        : "—"}
                    </td>
                    <td>{trade.symbol}</td>
                    <td
                      className={
                        trade.direction === "LONG" ? "text-green-400" : "text-red-400"
                      }
                    >
                      {trade.direction}
                    </td>
                    <td className="text-right">{trade.entry_price.toFixed(2)}</td>
                    <td className="text-right">
                      {trade.exit_price?.toFixed(2) ?? "—"}
                    </td>
                    <td
                      className={`text-right font-bold ${
                        (trade.pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {trade.pnl != null ? `$${trade.pnl.toFixed(2)}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Audit trail detail */}
        <div>
          {audit ? (
            <div className="text-xs space-y-3">
              <h2 className="font-bold text-sm">Audit Trail — Trade #{selectedId}</h2>
              <pre className="bg-gray-900 p-3 rounded overflow-auto max-h-[600px] text-gray-300">
                {JSON.stringify(audit, null, 2)}
              </pre>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">
              Select a trade to view its full audit trail
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
