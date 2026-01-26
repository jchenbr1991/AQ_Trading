// frontend/src/components/RecoveryPanel.tsx
import type { RecoveryStatus, RecoveryStageValue } from '../types';

interface RecoveryPanelProps {
  status: RecoveryStatus;
}

const STAGE_ORDER: RecoveryStageValue[] = [
  'connect_broker',
  'catchup_marketdata',
  'verify_risk',
  'ready',
];

const STAGE_LABELS: Record<RecoveryStageValue, string> = {
  connect_broker: 'Connect to Broker',
  catchup_marketdata: 'Catch Up Market Data',
  verify_risk: 'Verify Risk Limits',
  ready: 'Ready',
};

export function RecoveryPanel({ status }: RecoveryPanelProps) {
  const formatTime = (isoString: string) => {
    return new Date(isoString).toLocaleTimeString();
  };

  const getStageStatus = (stage: RecoveryStageValue) => {
    if (status.stages_completed.includes(stage)) {
      return 'completed';
    }
    if (stage === status.current_stage && !status.is_complete) {
      return 'current';
    }
    return 'pending';
  };

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-gray-900">Recovery Progress</h3>
        {status.is_complete && (
          <span className="px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800">
            Complete
          </span>
        )}
      </div>

      <div className="space-y-3">
        {STAGE_ORDER.map((stage) => {
          const stageStatus = getStageStatus(stage);
          return (
            <div key={stage} className="flex items-center space-x-3">
              {stageStatus === 'completed' && (
                <span className="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded-full bg-green-100 text-green-600">
                  ✓
                </span>
              )}
              {stageStatus === 'current' && (
                <span className="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded-full bg-blue-100 text-blue-600 animate-pulse">
                  ●
                </span>
              )}
              {stageStatus === 'pending' && (
                <span className="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded-full bg-gray-100 text-gray-400">
                  ○
                </span>
              )}
              <span className={`text-sm ${stageStatus === 'pending' ? 'text-gray-400' : 'text-gray-700'}`}>
                {STAGE_LABELS[stage]}
              </span>
            </div>
          );
        })}
      </div>

      <div className="mt-4 pt-3 border-t border-gray-200 text-xs text-gray-500">
        <p>Run ID: {status.run_id}</p>
        <p>Started: {formatTime(status.started_at)}</p>
      </div>
    </div>
  );
}
