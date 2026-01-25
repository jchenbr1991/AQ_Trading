// frontend/src/components/BacktestResults.tsx
import type { BacktestResult, EquityCurvePoint } from '../types';
import { EquityChart } from './EquityChart';
import { TraceTable } from './TraceTable';
import { SlippageStats } from './SlippageStats';

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

  const formatBenchmarkPercent = (value: string | number) => {
    const num = typeof value === 'string' ? parseFloat(value) : value;
    return `${(num * 100).toFixed(2)}%`;
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

      {/* Benchmark Comparison */}
      {result.benchmark && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            vs {result.benchmark.benchmark_symbol}
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-gray-500">Alpha (Ann.)</p>
              <p className="text-lg font-medium">{formatBenchmarkPercent(result.benchmark.alpha)}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Beta</p>
              <p className="text-lg font-medium">{parseFloat(result.benchmark.beta).toFixed(2)}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Information Ratio</p>
              <p className="text-lg font-medium">{parseFloat(result.benchmark.information_ratio).toFixed(2)}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Sortino Ratio</p>
              <p className="text-lg font-medium">{parseFloat(result.benchmark.sortino_ratio).toFixed(2)}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Tracking Error</p>
              <p className="text-lg font-medium">{formatBenchmarkPercent(result.benchmark.tracking_error)}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Up Capture</p>
              <p className="text-lg font-medium">{formatBenchmarkPercent(result.benchmark.up_capture)}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Down Capture</p>
              <p className="text-lg font-medium">{formatBenchmarkPercent(result.benchmark.down_capture)}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Benchmark Return</p>
              <p className="text-lg font-medium">{formatBenchmarkPercent(result.benchmark.benchmark_total_return)}</p>
            </div>
          </div>
        </div>
      )}

      {/* Equity Chart */}
      {equityCurve.length > 0 && <EquityChart data={equityCurve} />}

      {/* Execution Quality */}
      <SlippageStats traces={result.traces} />

      {/* Trade Details */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Trade Details</h3>
        <TraceTable traces={result.traces} />
      </div>
    </div>
  );
}
