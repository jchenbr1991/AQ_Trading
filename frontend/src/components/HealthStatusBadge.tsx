// frontend/src/components/HealthStatusBadge.tsx
import { HealthStatusValue } from '../types';

interface HealthStatusBadgeProps {
  status: HealthStatusValue;
  className?: string;
}

const statusStyles: Record<HealthStatusValue, string> = {
  healthy: 'bg-green-100 text-green-800',
  degraded: 'bg-yellow-100 text-yellow-800',
  down: 'bg-red-100 text-red-800',
  unknown: 'bg-gray-100 text-gray-800',
};

export function HealthStatusBadge({ status, className = '' }: HealthStatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusStyles[status]} ${className}`}
    >
      {status}
    </span>
  );
}
