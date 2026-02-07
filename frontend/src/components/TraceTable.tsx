// frontend/src/components/TraceTable.tsx
import type { SignalTrace } from '../types';

interface TraceTableProps {
  traces: SignalTrace[];
}

export function TraceTable({ traces }: TraceTableProps) {
  if (traces.length === 0) {
    return <p className="text-gray-500">No trades executed</p>;
  }

  return (
    <div className="bg-white rounded-lg shadow overflow-hidden">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Time</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Symbol</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Side</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Qty</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Expected</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Fill</th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Slippage (bps)</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {traces.map((trace) => (
            <tr key={trace.trace_id}>
              <td className="px-4 py-3 text-sm text-gray-900">
                {formatTimestamp(trace.signal_timestamp)}
              </td>
              <td className="px-4 py-3 text-sm text-gray-900">{trace.symbol}</td>
              <td className="px-4 py-3 text-sm">
                <span className={trace.signal_direction === 'buy' ? 'text-green-600' : 'text-red-600'}>
                  {trace.signal_direction.toUpperCase()}
                </span>
              </td>
              <td className="px-4 py-3 text-sm text-gray-900 text-right">{trace.signal_quantity}</td>
              <td className="px-4 py-3 text-sm text-gray-900 text-right">
                {trace.expected_price ? `$${parseFloat(trace.expected_price).toFixed(2)}` : '-'}
              </td>
              <td className="px-4 py-3 text-sm text-gray-900 text-right">
                {trace.fill_price ? `$${parseFloat(trace.fill_price).toFixed(2)}` : '-'}
              </td>
              <td className="px-4 py-3 text-sm text-right">
                {formatSlippageBps(trace.slippage_bps, trace.signal_direction)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Helper functions
function formatTimestamp(isoString: string): string {
  return new Date(isoString).toLocaleDateString();
}

function formatSlippageBps(bps: string | null, _direction: string): JSX.Element {
  if (bps === null) return <span>-</span>;
  const value = parseFloat(bps);
  // Positive slippage is bad (paid more / received less)
  const isUnfavorable = value > 0;
  return (
    <span className={isUnfavorable ? 'text-red-600' : 'text-green-600'}>
      {value > 0 ? '+' : ''}{value.toFixed(0)}
    </span>
  );
}
