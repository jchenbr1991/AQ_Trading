// frontend/src/pages/OptionsExpiringPage.tsx
import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAccountId } from '../contexts/AccountContext';
import { fetchExpiringAlerts, closePosition, acknowledgeAlert } from '../api/options';
import type { ExpiringAlertRow, ExpiringAlertsResponse } from '../types';
import { ConfirmModal } from '../components/ConfirmModal';

type SeverityColor = 'critical' | 'warning' | 'info';

const SEVERITY_COLORS: Record<SeverityColor, string> = {
  critical: 'border-l-red-500 bg-red-50',
  warning: 'border-l-yellow-500 bg-yellow-50',
  info: 'border-l-blue-500 bg-blue-50',
};

const SEVERITY_LABELS: Record<SeverityColor, string> = {
  critical: 'Critical',
  warning: 'Warning',
  info: 'Info',
};

function formatDTE(days: number): string {
  if (days === 0) return '今日收盘到期';
  if (days === 1) return '明日到期';
  return `${days} 天后到期`;
}

function formatExpiry(date: string): string {
  return new Date(date).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function SeverityBadge({ severity }: { severity: SeverityColor }) {
  return (
    <span
      className={`px-2 py-1 text-xs font-medium rounded ${
        severity === 'critical'
          ? 'bg-red-100 text-red-800'
          : severity === 'warning'
          ? 'bg-yellow-100 text-yellow-800'
          : 'bg-blue-100 text-blue-800'
      }`}
    >
      {SEVERITY_LABELS[severity]}
    </span>
  );
}

export function OptionsExpiringPage() {
  const [searchParams] = useSearchParams();
  const highlightAlertId = searchParams.get('alert_id');

  const [data, setData] = useState<ExpiringAlertsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [closeModalOpen, setCloseModalOpen] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState<ExpiringAlertRow | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const highlightRef = useRef<HTMLTableRowElement | null>(null);

  const accountId = useAccountId();

  // Fetch data on mount
  useEffect(() => {
    async function loadData() {
      try {
        setIsLoading(true);
        const result = await fetchExpiringAlerts({ accountId, status: 'pending' });
        setData(result);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load alerts');
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, [accountId]);

  // Scroll to highlighted alert
  useEffect(() => {
    if (highlightAlertId && highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // Flash animation
      highlightRef.current.classList.add('animate-pulse');
      setTimeout(() => {
        highlightRef.current?.classList.remove('animate-pulse');
      }, 2000);
    }
  }, [highlightAlertId, data]);

  const handleClose = (alert: ExpiringAlertRow) => {
    setSelectedAlert(alert);
    setCloseModalOpen(true);
  };

  const handleConfirmClose = async () => {
    if (!selectedAlert) return;

    setActionLoading(true);
    try {
      await closePosition(selectedAlert.position_id, { reason: 'expiring_soon' });
      // Refresh data
      const result = await fetchExpiringAlerts({ accountId, status: 'pending' });
      setData(result);
      setCloseModalOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to close position');
    } finally {
      setActionLoading(false);
    }
  };

  const handleAcknowledge = async (alert: ExpiringAlertRow) => {
    setActionLoading(true);
    try {
      await acknowledgeAlert(alert.alert_id);
      // Refresh data
      const result = await fetchExpiringAlerts({ accountId, status: 'pending' });
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to acknowledge alert');
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Expiring Options</h1>
        {data && (
          <div className="flex space-x-4 text-sm">
            <span className="text-red-600 font-medium">
              {data.summary.critical_count} Critical
            </span>
            <span className="text-yellow-600 font-medium">
              {data.summary.warning_count} Warning
            </span>
            <span className="text-blue-600 font-medium">
              {data.summary.info_count} Info
            </span>
          </div>
        )}
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
          {error}
        </div>
      )}

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Symbol</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Strike</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Type</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Expiry</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">DTE</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Qty</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Severity</th>
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
            ) : !data?.alerts || data.alerts.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-16 text-center text-gray-500">
                  <div className="text-lg">No expiring options</div>
                  <div className="text-sm mt-2">Enjoy your coffee!</div>
                </td>
              </tr>
            ) : (
              data.alerts.map((alert) => (
                <tr
                  key={alert.alert_id}
                  ref={alert.alert_id === highlightAlertId ? highlightRef : null}
                  className={`border-l-4 hover:bg-gray-50 ${
                    SEVERITY_COLORS[alert.severity as SeverityColor]
                  } ${alert.alert_id === highlightAlertId ? 'ring-2 ring-blue-400' : ''}`}
                >
                  <td className="px-4 py-3 font-medium text-gray-900">{alert.symbol}</td>
                  <td className="px-4 py-3 text-gray-700">${alert.strike.toFixed(2)}</td>
                  <td className="px-4 py-3 text-gray-700 uppercase">{alert.put_call}</td>
                  <td className="px-4 py-3 text-gray-700">{formatExpiry(alert.expiry_date)}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`font-medium ${
                        alert.days_to_expiry <= 1 ? 'text-red-600' : 'text-gray-700'
                      }`}
                    >
                      {formatDTE(alert.days_to_expiry)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{alert.quantity}</td>
                  <td className="px-4 py-3">
                    <SeverityBadge severity={alert.severity as SeverityColor} />
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    {alert.is_closable && (
                      <button
                        onClick={() => handleClose(alert)}
                        disabled={actionLoading}
                        className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                      >
                        Close
                      </button>
                    )}
                    <button
                      onClick={() => handleAcknowledge(alert)}
                      disabled={actionLoading}
                      className="px-3 py-1 text-sm bg-gray-200 text-gray-700 rounded hover:bg-gray-300 disabled:opacity-50"
                    >
                      Ignore
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <ConfirmModal
        isOpen={closeModalOpen}
        title="Close Position?"
        message={
          selectedAlert
            ? `Are you sure you want to close ${selectedAlert.symbol} ${selectedAlert.put_call.toUpperCase()} $${selectedAlert.strike}? This will create a sell order.`
            : ''
        }
        severity="critical"
        confirmText="Close Position"
        onConfirm={handleConfirmClose}
        onCancel={() => setCloseModalOpen(false)}
        isLoading={actionLoading}
      />
    </div>
  );
}
