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
