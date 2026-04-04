"use client";

import { useState, useCallback } from "react";
import * as api from "@/lib/api";

export function useOrders() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const placeBracket = useCallback(
    async (data: {
      symbol: string;
      side: string;
      quantity: number;
      order_type: string;
      entry_price?: number;
      stop_price: number;
      target_price: number;
    }) => {
      setLoading(true);
      setError(null);
      try {
        const result = await api.placeBracketOrder(data);
        return result;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Order failed");
        throw e;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const modify = useCallback(
    async (orderId: number, data: { limit_price?: number; stop_price?: number }) => {
      setLoading(true);
      setError(null);
      try {
        return await api.modifyOrder(orderId, data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Modify failed");
        throw e;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const cancel = useCallback(async (orderId: number) => {
    setLoading(true);
    setError(null);
    try {
      return await api.cancelOrder(orderId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancel failed");
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  const closePosition = useCallback(async (symbol: string, positionId?: number) => {
    setLoading(true);
    setError(null);
    try {
      return await api.closePosition(symbol, positionId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Close failed");
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  return { placeBracket, modify, cancel, closePosition, loading, error };
}
