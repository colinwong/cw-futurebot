const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }
  return res.json();
}

// Market Data
export function getCandles(symbol: string, barSize = "5 mins", duration = "1 D") {
  const params = new URLSearchParams({ bar_size: barSize, duration });
  return fetchApi<{ candles: Array<{ time: number; open: number; high: number; low: number; close: number; volume: number }> }>(
    `/api/market-data/${symbol}/candles?${params}`
  );
}

// Positions
export function getPositions(openOnly = true) {
  return fetchApi<{ positions: Array<Record<string, unknown>> }>(
    `/api/positions?open_only=${openOnly}`
  );
}

// Orders
export function getOrders(status?: string) {
  const params = status ? `?status=${status}` : "";
  return fetchApi<{ orders: Array<Record<string, unknown>> }>(`/api/orders${params}`);
}

export function placeBracketOrder(data: {
  symbol: string;
  side: string;
  quantity: number;
  order_type: string;
  entry_price?: number;
  stop_price: number;
  target_price: number;
}) {
  return fetchApi<{ entry_order_id: number; stop_order_id: number; target_order_id: number }>(
    "/api/orders/bracket",
    { method: "POST", body: JSON.stringify(data) }
  );
}

export function modifyOrder(orderId: number, data: { limit_price?: number; stop_price?: number; quantity?: number }) {
  return fetchApi<{ status: string }>(`/api/orders/${orderId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function cancelOrder(orderId: number) {
  return fetchApi<{ status: string }>(`/api/orders/${orderId}`, { method: "DELETE" });
}

export function closePosition(symbol: string) {
  return fetchApi<{ order_id: number }>(`/api/orders/close-position?symbol=${symbol}`, {
    method: "POST",
  });
}

// Trades
export function getTrades(params?: { symbol?: string; limit?: number; offset?: number }) {
  const searchParams = new URLSearchParams();
  if (params?.symbol) searchParams.set("symbol", params.symbol);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));
  const qs = searchParams.toString();
  return fetchApi<{ trades: Array<Record<string, unknown>> }>(`/api/trades${qs ? `?${qs}` : ""}`);
}

export function getTradeAudit(tradeId: number) {
  return fetchApi<Record<string, unknown>>(`/api/trades/${tradeId}/audit`);
}

// Signals
export function getSignals(params?: { symbol?: string; strategy?: string; action?: string; limit?: number }) {
  const searchParams = new URLSearchParams();
  if (params?.symbol) searchParams.set("symbol", params.symbol);
  if (params?.strategy) searchParams.set("strategy", params.strategy);
  if (params?.action) searchParams.set("action", params.action);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  return fetchApi<{ signals: Array<Record<string, unknown>> }>(`/api/signals${qs ? `?${qs}` : ""}`);
}

// Health
export function getHealth() {
  return fetchApi<{ status: string }>("/health");
}
