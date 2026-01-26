// frontend/src/components/AlertsTable.tsx
import { useState } from 'react';
import { useAlerts } from '../hooks';
import type { Alert, AlertSeverity } from '../types';

type FilterValue = 'all' | 1 | 2;

function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  const badgeClasses: Record<AlertSeverity, string> = {
    1: 'bg-red-100 text-red-800',
    2: 'bg-yellow-100 text-yellow-800',
    3: 'bg-blue-100 text-blue-800',
  };

  const labels: Record<AlertSeverity, string> = {
    1: 'SEV1',
    2: 'SEV2',
    3: 'SEV3',
  };

  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full ${badgeClasses[severity]}`}>
      {labels[severity]}
    </span>
  );
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function AlertsTable() {
  const [filter, setFilter] = useState<FilterValue>('all');

  const params = filter === 'all' ? {} : { severity: filter };
  const { data, isLoading, error } = useAlerts(params);

  const filterButtons: { value: FilterValue; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 1, label: 'SEV1' },
    { value: 2, label: 'SEV2' },
  ];

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-4 py-3 border-b flex items-center justify-between">
        <h2 className="text-lg font-semibold">Alert History</h2>
        <div className="flex space-x-2">
          {filterButtons.map((btn) => (
            <button
              key={btn.value}
              onClick={() => setFilter(btn.value)}
              className={`px-3 py-1 text-sm rounded ${
                filter === btn.value
                  ? 'bg-gray-800 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {btn.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 text-red-700">
          Failed to load alerts: {error.message}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Severity</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Type</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Summary</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Time</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Suppressed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {isLoading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                  Loading...
                </td>
              </tr>
            ) : !data?.alerts || data.alerts.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                  No alerts found
                </td>
              </tr>
            ) : (
              data.alerts.map((alert: Alert) => (
                <tr key={alert.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <SeverityBadge severity={alert.severity} />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">{alert.type}</td>
                  <td className="px-4 py-3 text-sm text-gray-600 max-w-md truncate">
                    {alert.summary}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {formatTime(alert.event_timestamp)}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500 text-right">
                    {alert.suppressed_count > 0 ? (
                      <span className="text-orange-600">+{alert.suppressed_count}</span>
                    ) : (
                      '-'
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {data && data.total > data.limit && (
        <div className="px-4 py-3 border-t text-sm text-gray-500 text-center">
          Showing {data.alerts.length} of {data.total} alerts
        </div>
      )}
    </div>
  );
}
