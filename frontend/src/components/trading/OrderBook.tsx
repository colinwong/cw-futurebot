"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useOrders } from "@/hooks/useOrders";
import { getOrders } from "@/lib/api";
import { formatTime } from "@/lib/timezone";
import type { Order } from "@/lib/types";

function orderLabel(order: Order): string {
  if (order.order_type === "MARKET") return "Market";
  if (order.order_type === "LIMIT") return `Limit @ ${order.limit_price?.toFixed(2)}`;
  if (order.order_type === "STOP") return `Stop @ ${order.stop_price?.toFixed(2)}`;
  if (order.order_type === "STOP_LIMIT") return `Stop Limit @ ${order.stop_price?.toFixed(2)}`;
  return order.order_type;
}

export default function OrderBook() {
  const [orders, setOrders] = useState<Order[]>([]);
  const { subscribe } = useWebSocket();
  const { cancel, loading } = useOrders();

  const fetchOrders = () => {
    getOrders("SUBMITTED")
      .then((res) => setOrders(res.orders as unknown as Order[]))
      .catch(console.error);
  };

  useEffect(() => { fetchOrders(); }, []);

  useEffect(() => {
    const unsub = subscribe("order", fetchOrders);
    return unsub;
  }, [subscribe]);

  if (orders.length === 0) return null;

  return (
    <div className="border-t border-gray-800 bg-gray-900 px-4 py-2">
      <div className="text-xs text-gray-500 mb-1">Working Orders</div>
      <div className="flex flex-col gap-1">
        {orders.map((order) => (
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
              {order.is_manual && (
                <span className="text-blue-400">MANUAL</span>
              )}
            </div>
            <button
              onClick={() => cancel(order.id)}
              disabled={loading}
              className="px-1.5 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded"
            >
              Cancel
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
