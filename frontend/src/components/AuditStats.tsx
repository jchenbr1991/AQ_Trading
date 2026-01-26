// frontend/src/components/AuditStats.tsx
import { useAuditStats } from '../hooks';

export function AuditStats() {
  const { data: stats, isLoading, error } = useAuditStats();

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
        <p className="text-red-700">Failed to load audit stats: {error.message}</p>
      </div>
    );
  }

  // Get top event types for display
  const eventTypes = stats?.by_event_type ?? {};
  const sortedEventTypes = Object.entries(eventTypes)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 3);

  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">Total Audit Logs</p>
        <p className="text-2xl font-bold">{stats?.total ?? 0}</p>
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">By Resource Type</p>
        <div className="text-sm mt-1 space-y-1">
          {Object.entries(stats?.by_resource_type ?? {})
            .sort(([, a], [, b]) => b - a)
            .slice(0, 3)
            .map(([type, count]) => (
              <div key={type} className="flex justify-between">
                <span className="text-gray-600">{type}</span>
                <span className="font-medium">{count}</span>
              </div>
            ))}
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">Top Event Types</p>
        <div className="text-sm mt-1 space-y-1">
          {sortedEventTypes.map(([type, count]) => (
            <div key={type} className="flex justify-between">
              <span className="text-gray-600 truncate mr-2">{type}</span>
              <span className="font-medium">{count}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">By Actor</p>
        <div className="text-sm mt-1 space-y-1">
          {Object.entries(stats?.by_actor ?? {})
            .sort(([, a], [, b]) => b - a)
            .slice(0, 3)
            .map(([actor, count]) => (
              <div key={actor} className="flex justify-between">
                <span className="text-gray-600 truncate mr-2">{actor}</span>
                <span className="font-medium">{count}</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
