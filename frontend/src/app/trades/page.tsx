"use client";

import { useState, useEffect } from "react";
import { getTrades, getTradeAudit } from "@/lib/api";
import { formatDateTime } from "@/lib/timezone";
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
          ) : trades.length === 0 ? (
            <div className="text-gray-500 text-sm">No closed trades yet</div>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="text-left py-1">Entry Time</th>
                  <th className="text-left">Symbol</th>
                  <th className="text-left">Dir</th>
                  <th className="text-right">Entry</th>
                  <th className="text-right">Exit</th>
                  <th className="text-right">P&L</th>
                  <th className="text-left pl-2">Exit Time</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => {
                  const hasPnl = trade.pnl != null;
                  const pnlColor = hasPnl
                    ? trade.pnl! >= 0 ? "text-green-400" : "text-red-400"
                    : "text-gray-600";

                  return (
                    <tr
                      key={trade.id}
                      onClick={() => handleSelect(trade.id)}
                      className={`cursor-pointer border-b border-gray-800 hover:bg-gray-900 ${
                        selectedId === trade.id ? "bg-gray-900" : ""
                      }`}
                    >
                      <td className="py-1 text-gray-500">
                        {trade.entry_timestamp
                          ? formatDateTime(trade.entry_timestamp)
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
                      <td className="text-right">
                        {trade.entry_price > 0 ? trade.entry_price.toFixed(2) : "—"}
                      </td>
                      <td className="text-right">
                        {trade.exit_price != null ? trade.exit_price.toFixed(2) : "—"}
                      </td>
                      <td className={`text-right font-bold ${pnlColor}`}>
                        {hasPnl ? `$${trade.pnl!.toFixed(2)}` : "—"}
                      </td>
                      <td className="pl-2 text-gray-500">
                        {trade.exit_timestamp
                          ? formatDateTime(trade.exit_timestamp)
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Audit trail detail */}
        <div>
          {audit ? (
            <div className="text-xs space-y-3">
              <h2 className="font-bold text-sm">Audit Trail — Trade #{selectedId}</h2>
              {renderAudit(audit)}
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

function renderAudit(audit: Record<string, unknown>) {
  const position = audit.position as Record<string, unknown> | null;
  const entryChain = audit.entry_chain as Record<string, unknown> | null;
  const outcome = audit.outcome as Record<string, unknown> | null;

  return (
    <div className="space-y-3">
      {/* Position summary */}
      {position && (
        <div className="bg-gray-900 p-3 rounded">
          <div className="font-bold text-gray-300 mb-1">Position</div>
          <div className="space-y-0.5 text-gray-400">
            <div>{position.direction as string} {position.symbol as string} x{position.quantity as number}</div>
            <div>Entry: {(position.entry_price as number) > 0 ? (position.entry_price as number).toFixed(2) : "—"}</div>
            <div>Exit: {position.exit_price != null ? (position.exit_price as number).toFixed(2) : "—"}</div>
            <div>Status: {position.is_open ? "Open" : "Closed"}</div>
          </div>
        </div>
      )}

      {/* Entry chain */}
      {entryChain && (
        <>
          {/* Market snapshot */}
          {entryChain.snapshot && (
            <div className="bg-gray-900 p-3 rounded">
              <div className="font-bold text-gray-300 mb-1">Market Snapshot at Entry</div>
              <div className="text-gray-400 space-y-0.5">
                {(() => {
                  const snap = entryChain.snapshot as Record<string, unknown>;
                  return (
                    <>
                      <div>Price: {(snap.price as number)?.toFixed(2)} | Bid: {(snap.bid as number)?.toFixed(2)} | Ask: {(snap.ask as number)?.toFixed(2)}</div>
                      {snap.timestamp && <div>Time: {formatDateTime(snap.timestamp as string)}</div>}
                    </>
                  );
                })()}
              </div>
            </div>
          )}

          {/* Signal */}
          {entryChain.signal && (
            <div className="bg-gray-900 p-3 rounded">
              <div className="font-bold text-gray-300 mb-1">Signal</div>
              <div className="text-gray-400 space-y-0.5">
                {(() => {
                  const sig = entryChain.signal as Record<string, unknown>;
                  return (
                    <>
                      <div>Strategy: {sig.strategy_name as string}</div>
                      <div>Direction: {sig.direction as string} | Strength: {(sig.strength as number)?.toFixed(2)}</div>
                      {sig.reasoning && (
                        <div className="text-gray-500 mt-1">
                          {(sig.reasoning as Record<string, string>).description || JSON.stringify(sig.reasoning)}
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            </div>
          )}

          {/* Decision */}
          {entryChain.decision && (
            <div className="bg-gray-900 p-3 rounded">
              <div className="font-bold text-gray-300 mb-1">Decision</div>
              <div className="text-gray-400 space-y-0.5">
                {(() => {
                  const dec = entryChain.decision as Record<string, unknown>;
                  return (
                    <>
                      <div>Action: <span className={dec.action === "EXECUTE" ? "text-green-400" : "text-orange-400"}>{dec.action as string}</span></div>
                      <div>Stop: {(dec.stop_price as number)?.toFixed(2)} | Target: {(dec.target_price as number)?.toFixed(2)}</div>
                      <div className="text-gray-500 mt-1">{dec.reasoning as string}</div>
                    </>
                  );
                })()}
              </div>
            </div>
          )}

          {/* Orders & Fills */}
          {(entryChain.orders as Array<Record<string, unknown>>)?.length > 0 && (
            <div className="bg-gray-900 p-3 rounded">
              <div className="font-bold text-gray-300 mb-1">Orders</div>
              <div className="space-y-1">
                {(entryChain.orders as Array<Record<string, unknown>>).map((order, i) => (
                  <div key={i} className="text-gray-400">
                    <span className={order.side === "BUY" ? "text-green-400" : "text-red-400"}>
                      {order.side as string}
                    </span>
                    {" "}{order.order_type as string} x{order.quantity as number}
                    {order.limit_price != null && ` @ ${(order.limit_price as number).toFixed(2)}`}
                    {order.stop_price != null && ` stop ${(order.stop_price as number).toFixed(2)}`}
                    {" — "}<span className="text-gray-500">{order.status as string}</span>
                    {(order.fills as Array<Record<string, unknown>>)?.map((fill, j) => (
                      <div key={j} className="text-gray-500 ml-4">
                        Filled: {(fill.fill_price as number).toFixed(2)} x{fill.quantity as number}
                        {fill.commission ? ` (comm: $${(fill.commission as number).toFixed(2)})` : ""}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* No entry chain (manual trade) */}
      {!entryChain && (
        <div className="bg-gray-900 p-3 rounded text-gray-500">
          Manual trade — no signal/decision audit trail
        </div>
      )}

      {/* Outcome */}
      {outcome && (
        <div className="bg-gray-900 p-3 rounded">
          <div className="font-bold text-gray-300 mb-1">Outcome</div>
          <div className="text-gray-400 space-y-0.5">
            <div>P&L: <span className={(outcome.pnl as number) >= 0 ? "text-green-400" : "text-red-400"}>
              ${(outcome.pnl as number).toFixed(2)}
            </span></div>
            {outcome.r_multiple != null && <div>R-Multiple: {(outcome.r_multiple as number).toFixed(2)}</div>}
            {outcome.hold_duration_seconds != null && (
              <div>Duration: {Math.round((outcome.hold_duration_seconds as number) / 60)} min</div>
            )}
            {outcome.analysis_notes != null && <div className="text-gray-500 mt-1">{String(outcome.analysis_notes)}</div>}
          </div>
        </div>
      )}
    </div>
  );
}
