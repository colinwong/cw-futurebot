"use client";

import { useState, useCallback } from "react";
import * as api from "@/lib/api";

export function useOrders() {
  const [placingOrder, setPlacingOrder] = useState(false);
  const [actionInProgress, setActionInProgress] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const isActionLoading = useCallback((key: string) => !!actionInProgress[key], [actionInProgress]);

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
      setPlacingOrder(true);
      setError(null);
      try {
        return await api.placeBracketOrder(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Order failed");
        throw e;
      } finally {
        setPlacingOrder(false);
      }
    },
    []
  );

  const modify = useCallback(
    async (orderId: number, data: { limit_price?: number; stop_price?: number }) => {
      const key = `modify-${orderId}`;
      setActionInProgress((p) => ({ ...p, [key]: true }));
      setError(null);
      try {
        return await api.modifyOrder(orderId, data);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Modify failed");
        throw e;
      } finally {
        setActionInProgress((p) => ({ ...p, [key]: false }));
      }
    },
    []
  );

  const cancel = useCallback(async (orderId: number) => {
    const key = `cancel-${orderId}`;
    setActionInProgress((p) => ({ ...p, [key]: true }));
    setError(null);
    try {
      return await api.cancelOrder(orderId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancel failed");
      throw e;
    } finally {
      setActionInProgress((p) => ({ ...p, [key]: false }));
    }
  }, []);

  const closePosition = useCallback(async (symbol: string, positionId?: number) => {
    const key = `close-${positionId || symbol}`;
    setActionInProgress((p) => ({ ...p, [key]: true }));
    setError(null);
    try {
      const result = await api.closePosition(symbol, positionId);
      // Keep loading state on success — position will disappear when fill processes
      return result;
    } catch (e) {
      setActionInProgress((p) => ({ ...p, [key]: false }));
      setError(e instanceof Error ? e.message : "Close failed");
      throw e;
    }
  }, []);

  return { placeBracket, modify, cancel, closePosition, placingOrder, isActionLoading, error };
}
