// frontend/src/components/SystemStatus.tsx
import type { SystemStatus as SystemStatusType, SystemModeValue } from '../types';

interface SystemStatusProps {
  status: SystemStatusType;
}

const modeConfig: Record<SystemModeValue, { label: string; bg: string; animate: boolean }> = {
  normal: { label: 'Normal', bg: 'bg-green-100 text-green-800', animate: false },
  degraded: { label: 'Degraded', bg: 'bg-yellow-100 text-yellow-800', animate: false },
  safe_mode: { label: 'Safe Mode', bg: 'bg-orange-100 text-orange-800', animate: true },
  safe_mode_disconnected: { label: 'Safe Mode (Disconnected)', bg: 'bg-red-100 text-red-800', animate: true },
  halt: { label: 'Halted', bg: 'bg-red-100 text-red-800', animate: true },
  recovering: { label: 'Recovering', bg: 'bg-blue-100 text-blue-800', animate: true },
};

export function SystemStatus({ status }: SystemStatusProps) {
  const config = modeConfig[status.mode];

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-medium text-gray-900">System Status</h3>
        <span
          className={`px-3 py-1 rounded-full text-sm font-medium ${config.bg} ${config.animate ? 'animate-pulse' : ''}`}
        >
          {config.label}
        </span>
      </div>

      <div className="space-y-2 text-sm text-gray-600">
        {status.stage && (
          <p>
            Recovery Stage: <span className="font-medium">{status.stage}</span>
          </p>
        )}

        {status.is_override && (
          <p className="text-orange-600">Override active</p>
        )}
      </div>
    </div>
  );
}
