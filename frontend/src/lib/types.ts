// Shared TypeScript types matching backend schemas

export type Symbol = "ES" | "NQ" | "MES" | "MNQ";
export type Direction = "LONG" | "SHORT";
export type OrderSide = "BUY" | "SELL";
export type OrderType = "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT";
export type OrderStatus = "PENDING" | "SUBMITTED" | "FILLED" | "CANCELLED" | "REJECTED";
export type DecisionAction = "EXECUTE" | "REJECT" | "MODIFY" | "DEFER";
export type Sentiment = "BULLISH" | "BEARISH" | "NEUTRAL";
export type ImpactRating = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Position {
  id: number;
  symbol: Symbol;
  direction: Direction;
  quantity: number;
  entry_price: number;
  entry_timestamp: string;
  exit_price: number | null;
  exit_timestamp: string | null;
  is_open: boolean;
  protective_order?: {
    status: string;
    verified_at: string | null;
  };
}

export interface Order {
  id: number;
  symbol: Symbol;
  side: OrderSide;
  order_type: OrderType;
  quantity: number;
  limit_price: number | null;
  stop_price: number | null;
  status: OrderStatus;
  ib_order_id: number | null;
  is_manual: boolean;
  timestamp: string;
}

export interface SignalRecord {
  id: number;
  timestamp: string;
  strategy_name: string;
  symbol: Symbol;
  direction: Direction;
  strength: number;
  reasoning: Record<string, unknown>;
  decision: {
    action: DecisionAction;
    reasoning: string;
    risk_evaluation: Record<string, unknown>;
    stop_price: number | null;
    target_price: number | null;
  } | null;
}

export interface TradeRecord {
  id: number;
  symbol: Symbol;
  direction: Direction;
  quantity: number;
  entry_price: number;
  exit_price: number | null;
  entry_timestamp: string;
  exit_timestamp: string | null;
  pnl: number | null;
  r_multiple: number | null;
  hold_duration_seconds: number | null;
}

export interface TradeAudit {
  position: {
    id: number;
    symbol: Symbol;
    direction: Direction;
    quantity: number;
    entry_price: number;
    exit_price: number | null;
    is_open: boolean;
  };
  entry_chain: {
    snapshot: {
      price: number;
      bid: number;
      ask: number;
      indicators: Record<string, unknown>;
      market_context: Record<string, unknown>;
      timestamp: string;
    } | null;
    signal: {
      strategy_name: string;
      direction: Direction;
      strength: number;
      reasoning: Record<string, unknown>;
    } | null;
    decision: {
      action: DecisionAction;
      risk_evaluation: Record<string, unknown>;
      reasoning: string;
      stop_price: number;
      target_price: number;
    };
    orders: Array<{
      id: number;
      side: OrderSide;
      order_type: OrderType;
      quantity: number;
      limit_price: number | null;
      stop_price: number | null;
      status: OrderStatus;
      fills: Array<{
        fill_price: number;
        quantity: number;
        commission: number;
        slippage: number;
        timestamp: string;
      }>;
    }>;
  } | null;
  outcome: {
    pnl: number;
    r_multiple: number | null;
    hold_duration_seconds: number;
    analysis_notes: string | null;
  } | null;
}

export interface NewsEvent {
  id: number;
  timestamp: string;
  source: string;
  url: string | null;
  headline: string;
  relevance_score: number;
  sentiment: Sentiment;
  impact_rating: ImpactRating;
  analysis: Record<string, unknown>;
  is_significant: boolean;
}

export interface AccountInfo {
  balance: number;
  unrealized_pnl: number;
  realized_pnl: number;
  margin_used: number;
  buying_power: number;
}

// WebSocket message types
export type WSEventType =
  | "candle"
  | "tick"
  | "position"
  | "order"
  | "signal"
  | "decision"
  | "news"
  | "account"
  | "system"
  | "strategy_eval"
  | "pong";

export interface WSMessage {
  type: WSEventType;
  data: unknown;
}

export interface TickData {
  symbol: Symbol;
  price: number;
  bid: number;
  ask: number;
  volume: number;
  timestamp: number;
}
