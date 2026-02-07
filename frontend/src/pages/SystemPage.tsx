// frontend/src/pages/SystemPage.tsx
import { useSystemStatus, useTradingPermissions } from '../hooks';
import { SystemStatus } from '../components/SystemStatus';
import { RecoveryPanel } from '../components/RecoveryPanel';

export function SystemPage() {
  const { data: status, isLoading: statusLoading, isError: statusError } = useSystemStatus();
  const { data: permissions, isLoading: permissionsLoading } = useTradingPermissions();

  const isLoading = statusLoading || permissionsLoading;

  if (isLoading) {
    return <p className="text-gray-500">Loading system status...</p>;
  }

  if (statusError || !status) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-600">Error loading system status</p>
      </div>
    );
  }

  return (
    <>
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">System Status</h1>
        <p className="text-sm text-gray-500 mt-1">
          Degradation mode and recovery status
        </p>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <SystemStatus status={status} />

        {status.mode === 'recovering' && status.stage && (
          <RecoveryPanel
            status={{
              run_id: 'current',
              current_stage: status.stage,
              stages_completed: [],
              started_at: new Date().toISOString(),
              is_complete: false,
            }}
          />
        )}
      </div>

      {/* Permissions Table */}
      {permissions && (
        <div className="bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Trading Permissions</h2>
          <div className="space-y-2">
            {Object.entries(permissions.permissions).map(([action, permission]) => (
              <div key={action} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                <span className="text-sm text-gray-700 capitalize">{action.replace(/_/g, ' ')}</span>
                <div className="flex items-center space-x-2">
                  {permission.warning && (
                    <span className="text-xs text-yellow-600">{permission.warning}</span>
                  )}
                  <span className={`text-sm font-medium ${permission.allowed ? 'text-green-600' : 'text-red-600'}`}>
                    {permission.allowed ? 'Allowed' : 'Denied'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
