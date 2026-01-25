// frontend/src/components/BacktestResults.tsx
import type { BacktestResult, EquityCurvePoint } from '../types';
import { EquityChart } from './EquityChart';

interface BacktestResultsProps {
  result: BacktestResult;
  equityCurve?: EquityCurvePoint[];
}

interface MetricCardProps {
  label: string;
  value: string;
  className?: string;
}

function MetricCard({ label, value, className = '' }: MetricCardProps) {
  return (
    <div className={`bg-white rounded-lg shadow p-4 ${className}`}>
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-xl font-semibold text-gray-900 mt-1">{value}</p>
    </div>
  );
}

export function BacktestResults({ result, equityCurve = [] }: BacktestResultsProps) {
  const formatCurrency = (value: string) => {
    const num = parseFloat(value);
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(num);
  };

  const formatPercent = (value: string) => {
    const num = parseFloat(value) * 100;
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`;
  };

  const formatRatio = (value: string) => {
    const num = parseFloat(value);
    return num.toFixed(2);
  };

  const totalReturn = parseFloat(result.total_return);
  const returnColorClass = totalReturn >= 0 ? 'text-green-600' : 'text-red-600';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-medium text-gray-900 mb-2">Backtest Results</h2>
        <div className="flex items-center gap-4">
          <span className={`text-3xl font-bold ${returnColorClass}`}>
            {formatPercent(result.total_return)}
          </span>
          <span className="text-gray-500">Total Return</span>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        <MetricCard label="Final Equity" value={formatCurrency(result.final_equity)} />
        <MetricCard label="Final Cash" value={formatCurrency(result.final_cash)} />
        <MetricCard label="Final Position" value={`${result.final_position_qty} shares`} />
        <MetricCard label="Annualized Return" value={formatPercent(result.annualized_return)} />
        <MetricCard label="Sharpe Ratio" value={formatRatio(result.sharpe_ratio)} />
        <MetricCard label="Max Drawdown" value={formatPercent(result.max_drawdown)} />
        <MetricCard label="Win Rate" value={formatPercent(result.win_rate)} />
        <MetricCard label="Total Trades" value={result.total_trades.toString()} />
        <MetricCard label="Avg Trade P&L" value={formatCurrency(result.avg_trade_pnl)} />
      </div>

      {/* Warm-up Info */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <p className="text-sm text-blue-800">
          <span className="font-medium">Warm-up Period:</span> {result.warm_up_bars_used} of{' '}
          {result.warm_up_required_bars} required bars used for strategy initialization
        </p>
      </div>

      {/* Equity Chart */}
      {equityCurve.length > 0 && <EquityChart data={equityCurve} />}
    </div>
  );
}
