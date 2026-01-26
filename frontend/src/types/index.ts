// frontend/src/types/index.ts

export interface AccountSummary {
  account_id: string;
  cash: number;
  buying_power: number;
  total_equity: number;
  unrealized_pnl: number;
  day_pnl: number;
  updated_at: string;
}

export interface Position {
  symbol: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  strategy_id: string | null;
}

export type TradingStateValue = 'RUNNING' | 'PAUSED' | 'HALTED';

export interface TradingState {
  state: TradingStateValue;
  since: string;
  changed_by: string;
  reason?: string;
  can_resume: boolean;
}

export interface KillSwitchResult {
  success: boolean;
  state: string;
  actions_executed: {
    halted: boolean;
    orders_cancelled: number;
    positions_flattened: number;
    flatten_orders: string[];
  };
  errors: string[];
  timestamp: string;
  triggered_by: string;
}

export interface ClosePositionRequest {
  symbol: string;
  quantity: number | 'all';
  order_type: 'market' | 'limit';
  limit_price?: number;
  time_in_force: 'GTC' | 'DAY' | 'IOC';
}

export interface ReconciliationAlert {
  timestamp: string;
  severity: 'info' | 'warning' | 'critical';
  type: string;
  symbol: string | null;
  local_value: string | null;
  broker_value: string | null;
  message: string;
}

export type FreshnessState = 'live' | 'stale' | 'error';

export type HealthStatusValue = 'healthy' | 'degraded' | 'down' | 'unknown';

export interface ComponentHealth {
  component: string;
  status: HealthStatusValue;
  latency_ms: number | null;
  last_check: string;
  message: string | null;
}

export interface SystemHealth {
  overall_status: HealthStatusValue;
  components: ComponentHealth[];
  checked_at: string;
}

// Trace types for signal analysis
export interface BarSnapshot {
  symbol: string;
  timestamp: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number;
}

export interface PortfolioSnapshot {
  cash: string;
  position_qty: number;
  position_avg_cost: string | null;
  equity: string;
}

export interface StrategySnapshot {
  strategy_class: string;
  params: Record<string, unknown>;
  state: Record<string, unknown>;
}

export interface SignalTrace {
  trace_id: string;
  signal_timestamp: string;
  symbol: string;
  signal_direction: string;
  signal_quantity: number;
  signal_reason: string | null;
  signal_bar: BarSnapshot;
  portfolio_state: PortfolioSnapshot;
  strategy_snapshot: StrategySnapshot | null;
  fill_bar: BarSnapshot | null;
  fill_timestamp: string | null;
  fill_quantity: number | null;
  fill_price: string | null;
  expected_price: string | null;
  expected_price_type: string | null;
  slippage: string | null;
  slippage_bps: string | null;
  commission: string | null;
}

// Backtest types
export interface BacktestRequest {
  strategy_class: string;
  strategy_params: Record<string, unknown>;
  symbol: string;
  start_date: string;
  end_date: string;
  initial_capital: string;
  slippage_bps?: number;
  commission_per_share?: string;
  benchmark_symbol?: string;
}

export interface BenchmarkComparison {
  benchmark_symbol: string;
  benchmark_total_return: string;
  alpha: string;
  beta: string;
  tracking_error: string;
  information_ratio: string;
  sortino_ratio: string;
  up_capture: string;
  down_capture: string;
}

export interface BacktestResult {
  final_equity: string;
  final_cash: string;
  final_position_qty: number;
  total_return: string;
  annualized_return: string;
  sharpe_ratio: string;
  max_drawdown: string;
  win_rate: string;
  total_trades: number;
  avg_trade_pnl: string;
  warm_up_required_bars: number;
  warm_up_bars_used: number;
  benchmark: BenchmarkComparison | null;
  traces: SignalTrace[];
}

export interface BacktestResponse {
  backtest_id: string;
  status: 'completed' | 'failed';
  result: BacktestResult | null;
  error: string | null;
}

export interface EquityCurvePoint {
  timestamp: string;
  equity: number;
}

// Alert types
export type AlertSeverity = 1 | 2 | 3;

export interface Alert {
  id: string;
  type: string;
  severity: AlertSeverity;
  summary: string;
  fingerprint: string;
  suppressed_count: number;
  event_timestamp: string;
  created_at: string;
  entity_account_id: string | null;
  entity_symbol: string | null;
}

export interface AlertListResponse {
  alerts: Alert[];
  total: number;
  offset: number;
  limit: number;
}

export interface AlertDelivery {
  id: string;
  channel: string;
  destination_key: string;
  attempt_number: number;
  status: 'pending' | 'sent' | 'failed';
  response_code: number | null;
  error_message: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface AlertStats {
  total_24h: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
  delivery_success_rate: number;
}

// Storage monitoring types
export interface TableStats {
  table_name: string;
  row_count: number;
  size_bytes: number;
  size_pretty: string;
  is_hypertable: boolean;
}

export interface CompressionStats {
  total_chunks: number;
  compressed_chunks: number;
  compression_ratio: number | null;
}

export interface StorageStats {
  database_size_bytes: number;
  database_size_pretty: string;
  timestamp: string;
  tables: TableStats[];
  compression: Record<string, CompressionStats>;
}
