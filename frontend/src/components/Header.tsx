import { useState } from 'react';
import { TradingStateBadge } from './TradingStateBadge';
import { ConfirmModal } from './ConfirmModal';
import type { TradingStateValue } from '../types';

interface HeaderProps {
  tradingState: TradingStateValue;
  onKillSwitch: () => Promise<void>;
}

export function Header({ tradingState, onKillSwitch }: HeaderProps) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleConfirm = async () => {
    setIsLoading(true);
    try {
      await onKillSwitch();
    } finally {
      setIsLoading(false);
      setShowConfirm(false);
    }
  };

  return (
    <>
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold text-gray-900">AQ Trading</h1>
            <TradingStateBadge state={tradingState} />
          </div>

          <button
            onClick={() => setShowConfirm(true)}
            disabled={tradingState === 'HALTED'}
            className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            ⚠️ Kill Switch
          </button>
        </div>
      </header>

      <ConfirmModal
        isOpen={showConfirm}
        title="Confirm Kill Switch"
        message={`This will immediately:
1. HALT all trading
2. CANCEL all pending orders
3. FLATTEN all positions (market)

System will remain HALTED until manually resumed.

Are you sure?`}
        severity="critical"
        onConfirm={handleConfirm}
        onCancel={() => setShowConfirm(false)}
        isLoading={isLoading}
      />
    </>
  );
}
