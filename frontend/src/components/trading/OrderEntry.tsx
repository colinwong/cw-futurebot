"use client";

import { useState } from "react";
import { useOrders } from "@/hooks/useOrders";
import type { Symbol } from "@/lib/types";

export default function OrderEntry() {
  const { placeBracket, loading, error } = useOrders();
  const [symbol, setSymbol] = useState<Symbol>("ES");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [quantity, setQuantity] = useState(1);
  const [orderType, setOrderType] = useState("MARKET");
  const [entryPrice, setEntryPrice] = useState("");
  const [stopPrice, setStopPrice] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccess(false);

    if (!stopPrice || !targetPrice) return;

    try {
      await placeBracket({
        symbol,
        side,
        quantity,
        order_type: orderType,
        entry_price: entryPrice ? parseFloat(entryPrice) : undefined,
        stop_price: parseFloat(stopPrice),
        target_price: parseFloat(targetPrice),
      });
      setSuccess(true);
      setStopPrice("");
      setTargetPrice("");
      setEntryPrice("");
    } catch {
      // error is set by hook
    }
  };

  return (
    <form onSubmit={handleSubmit} className="p-3 space-y-3">
      <div className="text-sm font-bold text-gray-300 mb-2">Order Entry</div>

      {/* Symbol selector */}
      <div className="flex gap-2">
        {(["ES", "NQ"] as Symbol[]).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSymbol(s)}
            className={`flex-1 py-1 text-xs rounded ${
              symbol === s ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Buy/Sell */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setSide("BUY")}
          className={`flex-1 py-1.5 text-sm font-bold rounded ${
            side === "BUY" ? "bg-green-600 text-white" : "bg-gray-800 text-gray-400"
          }`}
        >
          BUY
        </button>
        <button
          type="button"
          onClick={() => setSide("SELL")}
          className={`flex-1 py-1.5 text-sm font-bold rounded ${
            side === "SELL" ? "bg-red-600 text-white" : "bg-gray-800 text-gray-400"
          }`}
        >
          SELL
        </button>
      </div>

      {/* Quantity */}
      <div>
        <label className="text-xs text-gray-500">Qty</label>
        <input
          type="number"
          min={1}
          max={10}
          value={quantity}
          onChange={(e) => setQuantity(parseInt(e.target.value) || 1)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm"
        />
      </div>

      {/* Order type */}
      <div>
        <label className="text-xs text-gray-500">Type</label>
        <select
          value={orderType}
          onChange={(e) => setOrderType(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm"
        >
          <option value="MARKET">Market</option>
          <option value="LIMIT">Limit</option>
          <option value="STOP">Stop</option>
        </select>
      </div>

      {/* Entry price (for limit/stop orders) */}
      {orderType !== "MARKET" && (
        <div>
          <label className="text-xs text-gray-500">Entry Price</label>
          <input
            type="number"
            step="0.25"
            value={entryPrice}
            onChange={(e) => setEntryPrice(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm"
            placeholder="Entry price"
          />
        </div>
      )}

      {/* Stop price */}
      <div>
        <label className="text-xs text-gray-500">Stop Loss</label>
        <input
          type="number"
          step="0.25"
          value={stopPrice}
          onChange={(e) => setStopPrice(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm"
          placeholder="Stop price"
          required
        />
      </div>

      {/* Target price */}
      <div>
        <label className="text-xs text-gray-500">Profit Target</label>
        <input
          type="number"
          step="0.25"
          value={targetPrice}
          onChange={(e) => setTargetPrice(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm"
          placeholder="Target price"
          required
        />
      </div>

      {/* Submit */}
      <button
        type="submit"
        disabled={loading || !stopPrice || !targetPrice}
        className={`w-full py-2 text-sm font-bold rounded ${
          side === "BUY"
            ? "bg-green-600 hover:bg-green-700"
            : "bg-red-600 hover:bg-red-700"
        } text-white disabled:opacity-50`}
      >
        {loading ? "Placing..." : `Place Bracket ${side}`}
      </button>

      {error && <div className="text-xs text-red-400">{error}</div>}
      {success && <div className="text-xs text-green-400">Order placed</div>}
    </form>
  );
}
