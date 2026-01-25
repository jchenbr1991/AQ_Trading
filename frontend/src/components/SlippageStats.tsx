// frontend/src/components/SlippageStats.tsx
import type { SignalTrace } from '../types';

interface SlippageStatsProps {
  traces: SignalTrace[];
}

interface Stats {
  totalSlippage: number;  // $ amount
  avgSlippageBps: number;
  worstSlippageBps: number;
  unfavorablePercent: number;  // % of trades with positive slippage
}

export function SlippageStats({ traces }: SlippageStatsProps) {
  const stats = calculateStats(traces);

  if (traces.length === 0) {
    return null;
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-medium text-gray-900 mb-4">Execution Quality</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <p className="text-sm text-gray-500">Total Slippage</p>
          <p className={`text-lg font-medium ${stats.totalSlippage >= 0 ? 'text-red-600' : 'text-green-600'}`}>
            ${stats.totalSlippage.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Avg Slippage (bps)</p>
          <p className={`text-lg font-medium ${stats.avgSlippageBps >= 0 ? 'text-red-600' : 'text-green-600'}`}>
            {stats.avgSlippageBps >= 0 ? '+' : ''}{stats.avgSlippageBps.toFixed(1)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Worst Slippage (bps)</p>
          <p className="text-lg font-medium text-red-600">
            +{stats.worstSlippageBps.toFixed(1)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-500">Unfavorable Fills</p>
          <p className="text-lg font-medium">
            {stats.unfavorablePercent.toFixed(0)}%
          </p>
        </div>
      </div>
    </div>
  );
}

function calculateStats(traces: SignalTrace[]): Stats {
  const filledTraces = traces.filter(t => t.fill_price !== null && t.slippage !== null);

  if (filledTraces.length === 0) {
    return { totalSlippage: 0, avgSlippageBps: 0, worstSlippageBps: 0, unfavorablePercent: 0 };
  }

  // Total slippage in dollars
  const totalSlippage = filledTraces.reduce((sum, t) => {
    const slippage = parseFloat(t.slippage!);
    const qty = t.fill_quantity || 0;
    return sum + slippage * qty;
  }, 0);

  // Average slippage in bps
  const slippageBpsValues = filledTraces
    .filter(t => t.slippage_bps !== null)
    .map(t => parseFloat(t.slippage_bps!));
  const avgSlippageBps = slippageBpsValues.length > 0
    ? slippageBpsValues.reduce((a, b) => a + b, 0) / slippageBpsValues.length
    : 0;

  // Worst slippage (highest positive)
  const worstSlippageBps = Math.max(0, ...slippageBpsValues);

  // Percentage with unfavorable slippage (positive)
  const unfavorableCount = slippageBpsValues.filter(v => v > 0).length;
  const unfavorablePercent = (unfavorableCount / filledTraces.length) * 100;

  return { totalSlippage, avgSlippageBps, worstSlippageBps, unfavorablePercent };
}
