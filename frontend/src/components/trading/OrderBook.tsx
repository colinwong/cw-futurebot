"use client";

import { useState, useEffect } from "react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useOrders } from "@/hooks/useOrders";
import { getOrders } from "@/lib/api";
import type { Order } from "@/lib/types";

export default function OrderBook() {
  const [orders, setOrders] = useState<Order[]>([]);
  const { subscribe } = useWebSocket();
  const { cancel, loading } = useOrders();

  useEffect(() => {
    getOrders("SUBMITTED")
      .then((res) => setOrders(res.orders as unknown as Order[]))
      .catch(console.error);
  }, []);

  useEffect(() => {
    const unsub = subscribe("order", () => {
      getOrders("SUBMITTED")
        .then((res) => setOrders(res.orders as unknown as Order[]))
        .catch(console.error);
    });
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
                className={order.side === "BUY" ? "text-green-400" : "text-red-400"}
              >
                {order.side}
              </span>
              <span className="text-gray-300">{order.symbol}</span>
              <span className="text-gray-500">
                {order.order_type} x{order.quantity}
              </span>
              {order.limit_price && (
                <span className="text-gray-400">@ {order.limit_price.toFixed(2)}</span>
              )}
              {order.stop_price && (
                <span className="text-gray-400">stop {order.stop_price.toFixed(2)}</span>
              )}
              {order.is_manual && (
                <span className="text-blue-400 text-[10px]">MANUAL</span>
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
