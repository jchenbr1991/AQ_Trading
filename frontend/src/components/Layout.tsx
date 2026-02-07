import { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TradingStateBadge } from './TradingStateBadge';
import { ConfirmModal } from './ConfirmModal';
import { useTradingState } from '../hooks/useTradingState';
import type { TradingStateValue } from '../types';

const SIDEBAR_KEY = 'aq-sidebar-collapsed';

function KillSwitchButton({ tradingState, onKillSwitch }: { tradingState: TradingStateValue; onKillSwitch: () => Promise<void> }) {
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
      <button
        onClick={() => setShowConfirm(true)}
        disabled={tradingState === 'HALTED'}
        className="px-3 py-1.5 bg-red-600 text-white text-sm rounded hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
      >
        Kill Switch
      </button>
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

export function Layout() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === 'true';
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);

  const tradingState = useTradingState();

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, String(collapsed));
    } catch {
      // ignore
    }
  }, [collapsed]);

  const handleKillSwitch = async () => {
    await tradingState.triggerKillSwitch();
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <header className="fixed top-0 left-0 right-0 h-14 bg-white border-b border-gray-200 z-30 flex items-center px-4">
        <button
          onClick={() => setMobileOpen((o) => !o)}
          className="md:hidden mr-2 p-1.5 rounded text-gray-600 hover:bg-gray-100 hover:text-gray-900"
          aria-label="Toggle navigation"
        >
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
          </svg>
        </button>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-gray-900">AQ Trading</h1>
          <TradingStateBadge state={tradingState.data?.state ?? 'RUNNING'} />
        </div>
        <div className="ml-auto">
          <KillSwitchButton
            tradingState={tradingState.data?.state ?? 'RUNNING'}
            onKillSwitch={handleKillSwitch}
          />
        </div>
      </header>

      {/* Sidebar */}
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      {/* Main content */}
      <main
        className={`pt-14 transition-all duration-200 ml-0 ${
          collapsed ? 'md:ml-16' : 'md:ml-60'
        }`}
      >
        <div className="p-3 md:p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
