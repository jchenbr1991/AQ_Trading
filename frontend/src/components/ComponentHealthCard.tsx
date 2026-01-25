// frontend/src/components/ComponentHealthCard.tsx
import { ComponentHealth } from '../types';
import { HealthStatusBadge } from './HealthStatusBadge';

interface ComponentHealthCardProps {
  component: ComponentHealth;
}

export function ComponentHealthCard({ component }: ComponentHealthCardProps) {
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString();
  };

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-medium text-gray-900 capitalize">
          {component.component}
        </h3>
        <HealthStatusBadge status={component.status} />
      </div>

      <div className="space-y-1 text-sm text-gray-500">
        {component.latency_ms !== null && (
          <p>Latency: {component.latency_ms.toFixed(1)} ms</p>
        )}

        <p>Last check: {formatTime(component.last_check)}</p>

        {component.message && (
          <p className="text-red-600 mt-2">{component.message}</p>
        )}
      </div>
    </div>
  );
}
