// frontend/src/components/AlertStats.tsx
import { useAlertStats } from '../hooks';

export function AlertStats() {
  const { data: stats, isLoading, error } = useAlertStats();

  if (isLoading) {
    return (
      <div className="grid grid-cols-4 gap-4 mb-6">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-white rounded-lg shadow p-4 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-24 mb-2"></div>
            <div className="h-8 bg-gray-200 rounded w-16"></div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
        <p className="text-red-700">Failed to load alert stats: {error.message}</p>
      </div>
    );
  }

  const sev1Count = stats?.by_severity?.['1'] ?? 0;
  const sev2Count = stats?.by_severity?.['2'] ?? 0;
  const successRate = stats?.delivery_success_rate ?? 0;

  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">Total Alerts (24h)</p>
        <p className="text-2xl font-bold">{stats?.total_24h ?? 0}</p>
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">SEV1 Alerts</p>
        <p className="text-2xl font-bold text-red-600">{sev1Count}</p>
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">SEV2 Alerts</p>
        <p className="text-2xl font-bold text-yellow-600">{sev2Count}</p>
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">Delivery Success Rate</p>
        <p className="text-2xl font-bold text-green-600">
          {(successRate * 100).toFixed(1)}%
        </p>
      </div>
    </div>
  );
}
