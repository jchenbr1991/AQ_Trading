// frontend/src/pages/DerivativesPage.tsx
import { useState, useEffect } from 'react';
import { useExpiringPositions, useGenerateRollPlan } from '../hooks/useDerivatives';
import type { ExpirationAlertPosition, RollPlanResponse } from '../types';

function formatExpiry(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatDTE(days: number): string {
  if (days === 0) return 'Expires today';
  if (days === 1) return 'Expires tomorrow';
  return `${days} days`;
}

function ContractTypeBadge({ type }: { type: string }) {
  return (
    <span
      className={`px-2 py-1 text-xs font-medium rounded uppercase ${
        type === 'future'
          ? 'bg-purple-100 text-purple-800'
          : 'bg-blue-100 text-blue-800'
      }`}
    >
      {type}
    </span>
  );
}

function RollPlanModal({
  isOpen,
  plan,
  onClose,
}: {
  isOpen: boolean;
  plan: RollPlanResponse | null;
  onClose: () => void;
}) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !plan) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black bg-opacity-50" onClick={onClose} />
      <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
        <h2 className="text-xl font-bold mb-4">Roll Plan Generated</h2>
        <div className="space-y-3 text-sm">
          <div>
            <span className="font-medium">Symbol:</span> {plan.symbol}
          </div>
          <div>
            <span className="font-medium">Strategy:</span>{' '}
            <span className="capitalize">{plan.strategy.replace('_', ' ')}</span>
          </div>
          <div>
            <span className="font-medium">Close Action:</span> {plan.close_action}
          </div>
          {plan.open_action && (
            <div>
              <span className="font-medium">Open Action:</span> {plan.open_action}
            </div>
          )}
          <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-yellow-800">
            Note: This is a plan only. No trades have been executed.
          </div>
        </div>
        <div className="flex justify-end mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export function DerivativesPage() {
  const [daysFilter, setDaysFilter] = useState<number | undefined>(undefined);
  const { data, isLoading, isError, error } = useExpiringPositions(daysFilter);

  const rollPlanMutation = useGenerateRollPlan();
  const [rollPlan, setRollPlan] = useState<RollPlanResponse | null>(null);
  const [rollPlanModalOpen, setRollPlanModalOpen] = useState(false);

  const handleRoll = async (position: ExpirationAlertPosition) => {
    try {
      const plan = await rollPlanMutation.mutateAsync(position.symbol);
      setRollPlan(plan);
      setRollPlanModalOpen(true);
    } catch {
      // Error is handled by mutation state
    }
  };

  const handleCloseRollModal = () => {
    setRollPlanModalOpen(false);
    setRollPlan(null);
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Derivatives</h1>
        <div className="flex items-center space-x-4">
          <label className="text-sm text-gray-600">
            Days ahead:
            <select
              value={daysFilter ?? ''}
              onChange={(e) =>
                setDaysFilter(e.target.value ? parseInt(e.target.value, 10) : undefined)
              }
              className="ml-2 px-3 py-1 border border-gray-300 rounded text-sm"
            >
              <option value="">Default (5)</option>
              <option value="3">3 days</option>
              <option value="7">7 days</option>
              <option value="14">14 days</option>
              <option value="30">30 days</option>
            </select>
          </label>
          {data && (
            <span className="text-sm text-gray-500">
              {data.total} expiring position{data.total !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {isError && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {error instanceof Error ? error.message : 'Failed to load expiring positions'}
        </div>
      )}

      {rollPlanMutation.isError && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {rollPlanMutation.error instanceof Error
            ? rollPlanMutation.error.message
            : 'Failed to generate roll plan'}
        </div>
      )}

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Symbol</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Underlying</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Expiry</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">DTE</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Type</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Put/Call</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Strike</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {isLoading ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                  Loading...
                </td>
              </tr>
            ) : !data?.positions || data.positions.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-16 text-center text-gray-500">
                  <div className="text-lg">No expiring derivatives</div>
                  <div className="text-sm mt-2">
                    All positions are outside the {data?.warning_days ?? 5}-day warning window
                  </div>
                </td>
              </tr>
            ) : (
              data.positions.map((position) => (
                <tr
                  key={position.symbol}
                  className={`hover:bg-gray-50 ${
                    position.days_to_expiry <= 1
                      ? 'border-l-4 border-l-red-500 bg-red-50'
                      : position.days_to_expiry <= 3
                      ? 'border-l-4 border-l-yellow-500 bg-yellow-50'
                      : ''
                  }`}
                >
                  <td className="px-4 py-3 font-medium text-gray-900">{position.symbol}</td>
                  <td className="px-4 py-3 text-gray-700">{position.underlying}</td>
                  <td className="px-4 py-3 text-gray-700">{formatExpiry(position.expiry)}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`font-medium ${
                        position.days_to_expiry <= 1
                          ? 'text-red-600'
                          : position.days_to_expiry <= 3
                          ? 'text-yellow-600'
                          : 'text-gray-700'
                      }`}
                    >
                      {formatDTE(position.days_to_expiry)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <ContractTypeBadge type={position.contract_type} />
                  </td>
                  <td className="px-4 py-3 text-gray-700 uppercase">
                    {position.put_call ?? '-'}
                  </td>
                  <td className="px-4 py-3 text-gray-700">
                    {position.strike != null ? `$${position.strike.toFixed(2)}` : '-'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {position.contract_type === 'future' && (
                      <button
                        onClick={() => handleRoll(position)}
                        disabled={rollPlanMutation.isPending}
                        className="px-3 py-1 text-sm bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
                      >
                        {rollPlanMutation.isPending ? 'Rolling...' : 'Roll'}
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <RollPlanModal
        isOpen={rollPlanModalOpen}
        plan={rollPlan}
        onClose={handleCloseRollModal}
      />
    </div>
  );
}
