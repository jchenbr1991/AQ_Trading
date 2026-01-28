// frontend/src/components/GreeksAlertsPanel.tsx
import type { GreeksAlert, GreeksAlertLevel } from '../types';

interface GreeksAlertsPanelProps {
  alerts: GreeksAlert[];
  onAcknowledge?: (alertId: string) => void;
}

function getLevelBadgeClass(level: GreeksAlertLevel): string {
  switch (level) {
    case 'hard':
      return 'bg-red-100 text-red-800 border-red-200';
    case 'crit':
      return 'bg-orange-100 text-orange-800 border-orange-200';
    case 'warn':
      return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    default:
      return 'bg-gray-100 text-gray-800 border-gray-200';
  }
}

function getLevelLabel(level: GreeksAlertLevel): string {
  switch (level) {
    case 'hard':
      return 'HARD LIMIT';
    case 'crit':
      return 'CRITICAL';
    case 'warn':
      return 'WARNING';
    default:
      return 'NORMAL';
  }
}

export function GreeksAlertsPanel({ alerts, onAcknowledge }: GreeksAlertsPanelProps) {
  if (alerts.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent Alerts</h3>
        <div className="text-center py-8 text-gray-500">
          No active alerts
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent Alerts</h3>
      <div className="space-y-3">
        {alerts.slice(0, 5).map((alert) => (
          <div
            key={alert.alert_id}
            className={`p-3 rounded-lg border ${getLevelBadgeClass(alert.level)}`}
          >
            <div className="flex justify-between items-start">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-medium text-sm">
                    {getLevelLabel(alert.level)}
                  </span>
                  <span className="text-sm text-gray-600">
                    {alert.metric.toUpperCase()}
                  </span>
                </div>
                <p className="text-sm mt-1">{alert.message}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {new Date(alert.created_at).toLocaleString()}
                </p>
              </div>
              {!alert.acknowledged_at && onAcknowledge && (
                <button
                  onClick={() => onAcknowledge(alert.alert_id)}
                  className="text-xs px-2 py-1 bg-white rounded border hover:bg-gray-50"
                >
                  Acknowledge
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
