export type Horizon = "mid_term" | "long_term";
export type Signal = "strong_buy" | "watch" | "hold" | "sell_risk" | "insufficient_evidence";

export interface Stock {
  id: number;
  ticker: string;
  name: string;
  sector: string;
  industry: string;
  exchange: string;
  market_cap: number;
  avg_dollar_volume: number;
}

export interface Evidence {
  id: number;
  kind: string;
  source: string;
  source_url: string | null;
  observed_at: string;
  provider_timestamp: string;
  summary: string;
}

export interface Recommendation {
  id: number;
  stock: Stock;
  latest_price: number | null;
  horizon: Horizon;
  signal: Signal;
  opportunity_score: number;
  confidence_score: number;
  data_freshness: string;
  thesis: string;
  risk_summary: string;
  as_of: string;
  evidence: Evidence[];
}

export interface Holding {
  ticker: string;
  name: string;
  sector: string;
  quantity: number;
  cost_basis: number;
  latest_price: number;
  market_value: number;
  unrealized_return_pct: number;
}

export interface Portfolio {
  total_cost_basis: number;
  total_market_value: number;
  total_return_pct: number;
  holdings: Holding[];
  benchmarks: Record<string, number>;
}

export interface MockTrade {
  id: number;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  executed_at: string;
  note: string | null;
}

export interface ScanRun {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  universe_count: number;
  recommendations_count: number;
  notes: string | null;
}

export interface PerformancePoint {
  as_of: string;
  close: number;
}

export interface TradeMarker {
  side: "buy" | "sell";
  quantity: number;
  price: number;
  executed_at: string;
}

export interface StockPerformance {
  ticker: string;
  name: string;
  points: PerformancePoint[];
  markers: TradeMarker[];
}
