// Shared types for API requests and responses
export enum ModelProvider {
  OPENAI = 'OpenAI',
  ANTHROPIC = 'Anthropic',
  GROQ = 'Groq',
  OLLAMA = 'Ollama',
}

export interface AgentModelConfig {
  agent_id: string;
  model_name?: string;
  model_provider?: ModelProvider;
}

export interface GraphNode {
  id: string;
  type?: string;
  data?: Record<string, unknown>;
  position?: { x: number; y: number };
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type?: string;
  data?: Record<string, unknown>;
}

export interface PortfolioPosition {
  ticker: string;
  quantity: number;
  trade_price: number;
}

export interface AnalystSignal {
  signal?: string;
  confidence?: number;
  reasoning?: unknown;
  [key: string]: unknown;
}

export interface TradeDecision {
  action?: string;
  quantity?: number;
  confidence?: number;
  reasoning?: unknown;
  [key: string]: unknown;
}

export interface BacktestTickerDetail {
  ticker: string;
  action?: string;
  quantity?: number;
  price?: number;
  shares_owned?: number;
  long_shares?: number;
  short_shares?: number;
  position_value?: number;
  bullish_count?: number;
  bearish_count?: number;
  neutral_count?: number;
}

export interface BacktestPortfolioPosition {
  long: number;
  short: number;
  long_cost_basis: number;
  short_cost_basis: number;
}

export interface BacktestPerformanceMetrics {
  sharpe_ratio?: number;
  sortino_ratio?: number;
  max_drawdown?: number;
  max_drawdown_date?: string;
  long_short_ratio?: number;
  gross_exposure?: number;
  net_exposure?: number;
}

export interface BacktestPeriodResult {
  date: string;
  portfolio_value: number;
  cash: number;
  portfolio_return?: number;
  long_short_ratio?: number | null;
  ticker_details?: BacktestTickerDetail[];
  performance_metrics?: BacktestPerformanceMetrics;
}

// Base interface for shared fields between HedgeFundRequest and BacktestRequest
export interface BaseHedgeFundRequest {
  tickers: string[];
  graph_nodes: GraphNode[];
  graph_edges: GraphEdge[];
  agent_models?: AgentModelConfig[];
  model_name?: string;
  model_provider?: ModelProvider;
  margin_requirement?: number;
  portfolio_positions?: PortfolioPosition[];
}

export interface HedgeFundRequest extends BaseHedgeFundRequest {
  end_date?: string;
  start_date?: string;
  initial_cash?: number;
}

export interface BacktestRequest extends BaseHedgeFundRequest {
  start_date: string;
  end_date: string;
  initial_capital?: number;
}

export interface BacktestDayResult {
  date: string;
  portfolio_value: number;
  cash: number;
  decisions: Record<string, TradeDecision>;
  executed_trades: Record<string, number>;
  analyst_signals: Record<string, Record<string, AnalystSignal>>;
  current_prices: Record<string, number>;
  long_exposure: number;
  short_exposure: number;
  gross_exposure: number;
  net_exposure: number;
  long_short_ratio: number | null;
}
