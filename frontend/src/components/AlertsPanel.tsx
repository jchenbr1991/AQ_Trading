import type { ReconciliationAlert } from '../types';

interface AlertsPanelProps {
  alerts: ReconciliationAlert[] | undefined;
  isLoading: boolean;
}

export function AlertsPanel({ alerts, isLoading }: AlertsPanelProps) {
  const severityIcon = {
    critical: '🔴',
    warning: '🟡',
    info: '🟢',
  };

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-4 py-3 border-b">
        <h2 className="text-lg font-semibold">⚠️ Reconciliation Alerts</h2>
      </div>

      <div className="divide-y divide-gray-100 max-h-64 overflow-y-auto">
        {isLoading ? (
          <div className="px-4 py-8 text-center text-gray-500">Loading...</div>
        ) : !alerts || alerts.length === 0 ? (
          <div className="px-4 py-8 text-center text-gray-500">No recent alerts</div>
        ) : (
          alerts.map((alert, idx) => (
            <div key={idx} className="px-4 py-3 hover:bg-gray-50">
              <div className="flex items-start gap-3">
                <span className="text-lg">{severityIcon[alert.severity]}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-500">{formatTime(alert.timestamp)}</span>
                    <span className="font-medium text-gray-900">{alert.type}</span>
                    {alert.symbol && (
                      <span className="text-sm text-gray-600">{alert.symbol}</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 mt-1">{alert.message}</p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
