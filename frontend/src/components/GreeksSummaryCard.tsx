// frontend/src/components/GreeksSummaryCard.tsx
import type { AggregatedGreeks } from '../types';

interface GreeksSummaryCardProps {
  greeks: AggregatedGreeks;
  limits?: {
    delta: number;
    gamma: number;
    vega: number;
    theta: number;
  };
}

function formatGreek(value: number): string {
  if (Math.abs(value) >= 1000000) {
    return `${(value / 1000000).toFixed(2)}M`;
  }
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(1)}K`;
  }
  return value.toFixed(0);
}

function getUtilizationColor(pct: number): string {
  if (pct >= 120) return 'bg-red-600';
  if (pct >= 100) return 'bg-red-500';
  if (pct >= 80) return 'bg-yellow-500';
  return 'bg-green-500';
}

export function GreeksSummaryCard({ greeks, limits }: GreeksSummaryCardProps) {
  const defaultLimits = limits || { delta: 50000, gamma: 10000, vega: 20000, theta: 5000 };

  const metrics = [
    { label: 'Delta', value: greeks.dollar_delta, limit: defaultLimits.delta, unit: '' },
    { label: 'Gamma', value: greeks.gamma_dollar, limit: defaultLimits.gamma, unit: '' },
    { label: 'Vega', value: greeks.vega_per_1pct, limit: defaultLimits.vega, unit: '/1%' },
    { label: 'Theta', value: greeks.theta_per_day, limit: defaultLimits.theta, unit: '/day' },
  ];

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold text-gray-900">
          {greeks.scope === 'ACCOUNT' ? 'Account Greeks' : greeks.strategy_id}
        </h3>
        <div className="flex items-center space-x-2">
          <span className={`px-2 py-1 text-xs rounded ${
            greeks.is_coverage_sufficient ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
          }`}>
            {greeks.coverage_pct.toFixed(1)}% coverage
          </span>
          {greeks.staleness_seconds > 30 && (
            <span className="px-2 py-1 text-xs rounded bg-yellow-100 text-yellow-800">
              {greeks.staleness_seconds}s stale
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {metrics.map((metric) => {
          const utilization = (Math.abs(metric.value) / metric.limit) * 100;
          return (
            <div key={metric.label} className="space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">{metric.label}</span>
                <span className={`font-medium ${metric.value < 0 ? 'text-red-600' : 'text-gray-900'}`}>
                  ${formatGreek(metric.value)}{metric.unit}
                </span>
              </div>
              <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className={`h-full ${getUtilizationColor(utilization)} transition-all`}
                  style={{ width: `${Math.min(utilization, 100)}%` }}
                />
              </div>
              <div className="text-xs text-gray-400 text-right">
                {utilization.toFixed(0)}% of limit
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
