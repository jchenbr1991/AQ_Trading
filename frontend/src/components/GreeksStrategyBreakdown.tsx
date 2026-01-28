// frontend/src/components/GreeksStrategyBreakdown.tsx
import type { AggregatedGreeks } from '../types';

interface GreeksStrategyBreakdownProps {
  strategies: Record<string, AggregatedGreeks>;
  onSelectStrategy?: (strategyId: string) => void;
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

export function GreeksStrategyBreakdown({
  strategies,
  onSelectStrategy,
}: GreeksStrategyBreakdownProps) {
  const strategyList = Object.entries(strategies).sort(
    ([, a], [, b]) => Math.abs(b.dollar_delta) - Math.abs(a.dollar_delta)
  );

  if (strategyList.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">By Strategy</h3>
        <div className="text-center py-8 text-gray-500">
          No strategy breakdown available
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">By Strategy</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr className="text-xs text-gray-500 uppercase border-b">
              <th className="text-left py-2">Strategy</th>
              <th className="text-right py-2">Delta</th>
              <th className="text-right py-2">Gamma</th>
              <th className="text-right py-2">Vega</th>
              <th className="text-right py-2">Theta</th>
              <th className="text-right py-2">Legs</th>
            </tr>
          </thead>
          <tbody>
            {strategyList.map(([strategyId, greeks]) => (
              <tr
                key={strategyId}
                className="border-b hover:bg-gray-50 cursor-pointer"
                onClick={() => onSelectStrategy?.(strategyId)}
              >
                <td className="py-3 font-medium">
                  {strategyId === '_unassigned_' ? '(Unassigned)' : strategyId}
                </td>
                <td className={`text-right ${greeks.dollar_delta < 0 ? 'text-red-600' : ''}`}>
                  ${formatGreek(greeks.dollar_delta)}
                </td>
                <td className={`text-right ${greeks.gamma_dollar < 0 ? 'text-red-600' : ''}`}>
                  ${formatGreek(greeks.gamma_dollar)}
                </td>
                <td className={`text-right ${greeks.vega_per_1pct < 0 ? 'text-red-600' : ''}`}>
                  ${formatGreek(greeks.vega_per_1pct)}
                </td>
                <td className={`text-right ${greeks.theta_per_day < 0 ? 'text-red-600' : ''}`}>
                  ${formatGreek(greeks.theta_per_day)}
                </td>
                <td className="text-right text-gray-500">
                  {greeks.valid_legs_count}/{greeks.total_legs_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
