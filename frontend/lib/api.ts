// Same-origin on Railway: leave empty. Local docker/dev: http://localhost:8000
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (typeof parsed.detail === "string") throw new Error(parsed.detail);
      throw new Error(text || res.statusText);
    } catch (e) {
      if (e instanceof SyntaxError) throw new Error(text || res.statusText);
      throw e;
    }
  }
  return res.json() as Promise<T>;
}

export type Health = {
  status: string;
  environment: string;
  trading_mode: string;
  providers: { name: string; available: boolean }[];
};

export type Symbol = {
  id: number;
  ticker: string;
  name?: string;
  exchange?: string;
  asset_type: string;
  currency: string;
};

export type Bar = {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: string;
};

export type Macro = {
  series_code: string;
  ts: string;
  value: number;
  source: string;
};

export type Prediction = {
  id: number;
  model_name: string;
  horizon: string;
  predicted_at: string;
  predicted_price?: number;
  direction?: string;
  confidence?: number;
};

export type Signal = {
  id: number;
  signal_type: string;
  strength?: number;
  rationale?: string;
  status: string;
  created_at: string;
};

export type Order = {
  id: number;
  side: string;
  quantity: number;
  status: string;
  mode: string;
  avg_fill_price?: number;
  created_at: string;
};

export type Position = {
  id: number;
  symbol_id: number;
  ticker?: string;
  quantity: number;
  avg_cost?: number;
  unrealized_pnl: number;
  realized_pnl: number;
};

export type RiskEvent = {
  id: number;
  event_type: string;
  severity: string;
  message: string;
  created_at: string;
  acknowledged: boolean;
};

export type SnsPost = {
  id: number;
  platform: string;
  content: string;
  status: string;
  related_symbol?: string;
  created_at: string;
};

export type TechnicalResponse = {
  ticker: string;
  snapshot: Record<string, number | string | null>;
  series: {
    ts: string;
    close: number;
    sma_20?: number | null;
    ema_12?: number | null;
    rsi_14?: number | null;
    macd?: number | null;
    bb_upper?: number | null;
    bb_lower?: number | null;
    volume: number;
  }[];
};

export type Fundamentals = {
  ticker: string;
  per?: number | null;
  pbr?: number | null;
  roe?: number | null;
  roa?: number | null;
  eps?: number | null;
  bps?: number | null;
  operating_margin?: number | null;
  equity_ratio?: number | null;
  market_cap?: number | null;
};

export type NewsItem = {
  id: number;
  source: string;
  category: string;
  title: string;
  url?: string;
  sentiment?: number | null;
  sentiment_label?: string | null;
  summary?: string | null;
};

export type BacktestResult = {
  id?: number;
  engine: string;
  strategy: string;
  metrics: Record<string, number | null>;
  equity_curve: { ts: string; equity: number; buy_hold?: number; drawdown?: number }[];
  drawdown_curve?: { ts: string; drawdown: number }[];
  warning?: string;
};

export type AccuracyPoint = {
  ts: string;
  close: number;
  predicted_price: number;
  actual_price: number;
  predicted_return: number;
  actual_return: number;
  predicted_direction: string;
  actual_direction: string;
  correct: boolean;
  confidence: number;
  error: number;
  model_equity?: number;
  buy_hold_equity?: number;
};

export type AccuracyResult = {
  ticker: string;
  model?: string;
  horizon?: string;
  n_samples?: number;
  metrics: Record<string, number | null>;
  confusion?: { tp: number; tn: number; fp: number; fn: number };
  series: AccuracyPoint[];
  error?: string;
};

export type IntegratedAnalysis = {
  ticker: string;
  as_of: string;
  signal: "buy" | "sell" | "hold" | string;
  composite_score: number;
  strength: number;
  weights: { technical: number; fundamental: number; news: number };
  scores: { technical: number; fundamental: number; news: number };
  summary: string;
  technical: { score: number; snapshot: Record<string, unknown>; reasons: string[] };
  fundamental: { score: number; metrics: Fundamentals | null; reasons: string[] };
  news: {
    score: number;
    meta: { count: number; avg_sentiment?: number | null; labels?: Record<string, number> };
    articles: NewsItem[];
    reasons: string[];
  };
  radar: { axis: string; value: number }[];
};

export type PipelineResult = {
  ticker: string;
  status?: string;
  stages: Record<string, unknown>;
  error?: string;
};

export const api = {
  health: () => request<Health>("/health"),
  symbols: () => request<Symbol[]>("/symbols"),
  macro: () => request<Macro[]>("/macro"),
  bars: (ticker: string) => request<Bar[]>(`/market/${encodeURIComponent(ticker)}/bars?limit=90`),
  predictions: () => request<Prediction[]>("/predictions"),
  signals: () => request<Signal[]>("/signals"),
  orders: () => request<Order[]>("/orders"),
  positions: () => request<Position[]>("/positions"),
  risk: () => request<RiskEvent[]>("/risk/events"),
  sns: () => request<SnsPost[]>("/sns/posts"),
  ingest: (ticker: string) =>
    request("/ingest/bars", { method: "POST", body: JSON.stringify({ ticker, timeframe: "1d", limit: 120 }) }),
  runPipeline: (ticker: string, quantity = 100) =>
    request<PipelineResult>("/pipeline/run", {
      method: "POST",
      body: JSON.stringify({ ticker, quantity }),
    }),
  technical: (ticker: string) => request<TechnicalResponse>(`/technical/${encodeURIComponent(ticker)}`),
  fundamentalsIngest: (ticker: string) =>
    request<Fundamentals>("/fundamentals/ingest", { method: "POST", body: JSON.stringify({ ticker }) }),
  fundamentals: (ticker: string) => request<Fundamentals>(`/fundamentals/${encodeURIComponent(ticker)}`),
  newsCollect: (ticker: string) =>
    request("/news/collect", { method: "POST", body: JSON.stringify({ ticker }) }),
  news: () => request<NewsItem[]>("/news"),
  mlPredict: (ticker: string) =>
    request<Record<string, unknown>>("/ml/predict", { method: "POST", body: JSON.stringify({ ticker }) }),
  dlPredict: (ticker: string, model = "lstm") =>
    request<Record<string, unknown>>("/dl/predict", {
      method: "POST",
      body: JSON.stringify({ ticker, model, backend: "pytorch", epochs: 8 }),
    }),
  backtest: (ticker: string, engine = "pandas") =>
    request<BacktestResult>("/backtest/run", {
      method: "POST",
      body: JSON.stringify({ ticker, engine, fast: 10, slow: 30 }),
    }),
  accuracy: (ticker: string) =>
    request<AccuracyResult>("/accuracy/evaluate", {
      method: "POST",
      body: JSON.stringify({ ticker, min_train: 40, max_points: 80 }),
    }),
  integrated: (ticker: string, collectNews = true) =>
    request<IntegratedAnalysis>("/analysis/integrated", {
      method: "POST",
      body: JSON.stringify({ ticker, collect_news: collectNews }),
    }),
  brokers: () => request<{ name: string; available: boolean }[]>("/brokers"),
  ragQuery: (question: string) =>
    request<{ answer?: string; context?: string; hits?: unknown[] }>("/rag/query", {
      method: "POST",
      body: JSON.stringify({ question, limit: 5, session_id: "web" }),
    }),
};
