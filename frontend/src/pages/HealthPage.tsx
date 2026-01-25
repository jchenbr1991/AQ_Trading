// frontend/src/pages/HealthPage.tsx
import { useHealth } from '../hooks/useHealth';
import { HealthStatusBadge } from '../components/HealthStatusBadge';
import { ComponentHealthCard } from '../components/ComponentHealthCard';

export function HealthPage() {
  const { data, isLoading, isError } = useHealth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-100 p-8">
        <div className="max-w-4xl mx-auto">
          <p className="text-gray-500">Loading health status...</p>
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="min-h-screen bg-gray-100 p-8">
        <div className="max-w-4xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-600">Error loading health status</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-gray-900">System Health</h1>
            <HealthStatusBadge status={data.overall_status} className="text-sm" />
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Last checked: {new Date(data.checked_at).toLocaleString()}
          </p>
        </div>

        {/* Components Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.components.map((component) => (
            <ComponentHealthCard key={component.component} component={component} />
          ))}
        </div>

        {/* Empty state */}
        {data.components.length === 0 && (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
            No health checks configured
          </div>
        )}
      </div>
    </div>
  );
}
