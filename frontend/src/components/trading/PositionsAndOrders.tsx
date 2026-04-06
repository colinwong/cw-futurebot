"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useOrders } from "@/hooks/useOrders";
import { getPositions, getOrders } from "@/lib/api";
import { formatTime } from "@/lib/timezone";
import type { Order } from "@/lib/types";

interface PositionData {
  id: number;
  symbol: string;
  direction: string;
  quantity: number;
  entry_price: number;
  margin_deployed: number | null;
  risk_amount: number | null;
  stop_price: number | null;
  target_price: number | null;
  stop_ib_order_id: number | null;
  target_ib_order_id: number | null;
  entry_timestamp: string;
  is_open: boolean;
  protective_status: string | null;
}

function formatDollar(value: number | null): string {
  if (value == null) return "—";
  return value.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function orderLabel(order: Order): string {
  if (order.order_type === "MARKET") return "Market";
  if (order.order_type === "LIMIT") return `Limit @ ${order.limit_price?.toFixed(2)}`;
  if (order.order_type === "STOP") return `Stop @ ${order.stop_price?.toFixed(2)}`;
  return order.order_type;
}

export default function PositionsAndOrders() {
  const [positions, setPositions] = useState<PositionData[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const { subscribe } = useWebSocket();
  const { closePosition, cancel, isActionLoading, error } = useOrders();

  const fetchAll = () => {
    getPositions(true)
      .then((res) => setPositions(res.positions as unknown as PositionData[]))
      .catch(console.error);
    getOrders("SUBMITTED")
      .then((res) => setOrders(res.orders as unknown as Order[]))
      .catch(console.error);
  };

  useEffect(() => { fetchAll(); }, []);

  useEffect(() => {
    const unsubs = [
      subscribe("position", fetchAll),
      subscribe("order", fetchAll),
    ];
    return () => unsubs.forEach((u) => u());
  }, [subscribe]);

  // Group orders under their parent position
  const positionOrderIds = new Set<number>();
  for (const pos of positions) {
    if (pos.stop_ib_order_id) positionOrderIds.add(pos.stop_ib_order_id);
    if (pos.target_ib_order_id) positionOrderIds.add(pos.target_ib_order_id);
  }

  // Orders that belong to a position's bracket
  const getChildOrders = (pos: PositionData): Order[] => {
    return orders.filter(
      (o) => o.ib_order_id === pos.stop_ib_order_id || o.ib_order_id === pos.target_ib_order_id
    );
  };

  // Standalone orders not linked to any position
  const standaloneOrders = orders.filter(
    (o) => !positionOrderIds.has(o.ib_order_id ?? -1)
  );

  if (positions.length === 0 && standaloneOrders.length === 0) return null;

  // Show error banner if any action failed
  const errorBanner = error ? (
    <div className="text-xs text-red-400 bg-red-900/30 px-3 py-1 rounded mb-1">{error}</div>
  ) : null;

  return (
    <div className="border-t border-gray-800 bg-gray-900 px-4 py-2">
      {errorBanner}
      {/* Positions with grouped orders */}
      {positions.length > 0 && (
        <>
          <div className="text-xs text-gray-500 mb-1">Open Positions</div>
          <div className="flex flex-col gap-2 mb-2">
            {positions.map((pos) => {
              const children = getChildOrders(pos);
              return (
                <div key={pos.id} className="bg-gray-950 rounded px-3 py-2">
                  {/* Position header */}
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-3">
                      <span
                        className={`font-bold ${
                          pos.direction === "LONG" ? "text-green-400" : "text-red-400"
                        }`}
                      >
                        {pos.direction} {pos.symbol} x{pos.quantity}
                      </span>
                      <span className="text-gray-300">
                        Entry: {pos.entry_price > 0 ? pos.entry_price.toFixed(2) : "MKT (pending)"}
                      </span>
                      {pos.margin_deployed != null && (
                        <span className="text-yellow-400" title="Margin deployed (qty × margin per contract)">
                          Margin: {formatDollar(pos.margin_deployed)}
                        </span>
                      )}
                      {pos.stop_price && (
                        <span className="text-red-400">Stop: {pos.stop_price.toFixed(2)}</span>
                      )}
                      {pos.target_price && (
                        <span className="text-green-400">Target: {pos.target_price.toFixed(2)}</span>
                      )}
                      {pos.risk_amount != null && (
                        <span className="text-orange-400" title="Max risk (distance to stop × qty × multiplier)">
                          Risk: {formatDollar(pos.risk_amount)}
                        </span>
                      )}
                      <span className="text-gray-600">{formatTime(pos.entry_timestamp)}</span>
                    </div>
                    <button
                      onClick={async () => {
                        try {
                          await closePosition(pos.symbol, pos.id);
                          fetchAll();
                        } catch { /* error shown in banner */ }
                      }}
                      disabled={isActionLoading(`close-${pos.id}`)}
                      className="px-2 py-0.5 text-xs bg-red-900 hover:bg-red-800 text-red-300 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isActionLoading(`close-${pos.id}`) ? "Closing..." : "Close"}
                    </button>
                  </div>

                  {/* Child orders (stop/target) */}
                  {children.length > 0 && (
                    <div className="mt-1.5 ml-4 border-l border-gray-800 pl-3 space-y-0.5">
                      {children.map((order) => (
                        <div key={order.id} className="flex items-center justify-between text-xs">
                          <div className="flex items-center gap-2">
                            <span className="text-gray-600">└</span>
                            <span
                              className={order.side === "BUY" ? "text-green-400" : "text-red-400"}
                            >
                              {order.side}
                            </span>
                            <span className="text-gray-400">{orderLabel(order)}</span>
                            <span className="text-gray-600">{order.status}</span>
                          </div>
                          <button
                            onClick={async () => {
                              try { await cancel(order.id); fetchAll(); } catch {}
                            }}
                            disabled={isActionLoading(`cancel-${order.id}`)}
                            className="px-1.5 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded text-xs disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {isActionLoading(`cancel-${order.id}`) ? "..." : "Cancel"}
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Standalone orders (not linked to a position) */}
      {standaloneOrders.length > 0 && (
        <>
          <div className="text-xs text-gray-500 mb-1">Working Orders</div>
          <div className="flex flex-col gap-0.5">
            {standaloneOrders.map((order) => (
              <div key={order.id} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span
                    className={`font-bold ${order.side === "BUY" ? "text-green-400" : "text-red-400"}`}
                  >
                    {order.side}
                  </span>
                  <span className="text-gray-300">{order.symbol}</span>
                  <span className="text-gray-300">x{order.quantity}</span>
                  <span className="text-gray-400">{orderLabel(order)}</span>
                  <span className="text-gray-600">{formatTime(order.timestamp)}</span>
                </div>
                <button
                  onClick={async () => {
                    try { await cancel(order.id); fetchAll(); } catch {}
                  }}
                  disabled={isActionLoading(`cancel-${order.id}`)}
                  className="px-1.5 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isActionLoading(`cancel-${order.id}`) ? "..." : "Cancel"}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
