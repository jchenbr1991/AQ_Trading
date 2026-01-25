import { useState } from 'react';
import { ConfirmModal } from './ConfirmModal';
import { FreshnessIndicator } from './FreshnessIndicator';
import type { Position, TradingStateValue, FreshnessState } from '../types';

interface PositionsTableProps {
  positions: Position[] | undefined;
  isLoading: boolean;
  tradingState: TradingStateValue;
  freshness: { state: FreshnessState; ageSeconds: number };
  onClosePosition: (symbol: string) => Promise<void>;
}

export function PositionsTable({
  positions,
  isLoading,
  tradingState,
  freshness,
  onClosePosition,
}: PositionsTableProps) {
  const [closingSymbol, setClosingSymbol] = useState<string | null>(null);
  const [isClosing, setIsClosing] = useState(false);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(value);
  };

  const handleConfirmClose = async () => {
    if (!closingSymbol) return;
    setIsClosing(true);
    try {
      await onClosePosition(closingSymbol);
    } finally {
      setIsClosing(false);
      setClosingSymbol(null);
    }
  };

  const canClose = tradingState !== 'HALTED';

  return (
    <>
      <div className="bg-white rounded-lg shadow mb-6">
        <div className="px-4 py-3 border-b flex items-center justify-between">
          <h2 className="text-lg font-semibold">Positions</h2>
          <FreshnessIndicator state={freshness.state} ageSeconds={freshness.ageSeconds} />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Symbol</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Qty</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Avg Cost</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Current</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">P&L</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                    Loading...
                  </td>
                </tr>
              ) : !positions || positions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                    No positions
                  </td>
                </tr>
              ) : (
                positions.map((pos) => (
                  <tr key={pos.symbol} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">{pos.symbol}</td>
                    <td className="px-4 py-3 text-right">{pos.quantity}</td>
                    <td className="px-4 py-3 text-right">{formatCurrency(pos.avg_cost)}</td>
                    <td className="px-4 py-3 text-right">{formatCurrency(pos.current_price)}</td>
                    <td className={`px-4 py-3 text-right font-medium ${
                      pos.unrealized_pnl >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {pos.unrealized_pnl >= 0 ? '+' : ''}{formatCurrency(pos.unrealized_pnl)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setClosingSymbol(pos.symbol)}
                        disabled={!canClose}
                        className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Close
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <ConfirmModal
        isOpen={!!closingSymbol}
        title={`Close ${closingSymbol} Position?`}
        message={`This will submit a market order to close your entire ${closingSymbol} position.`}
        severity="warning"
        onConfirm={handleConfirmClose}
        onCancel={() => setClosingSymbol(null)}
        isLoading={isClosing}
      />
    </>
  );
}
