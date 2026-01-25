// frontend/src/components/FreshnessIndicator.tsx
import type { FreshnessState } from '../types';

interface FreshnessIndicatorProps {
  state: FreshnessState;
  ageSeconds: number;
  lastUpdated?: string;
}

export function FreshnessIndicator({ state, ageSeconds, lastUpdated }: FreshnessIndicatorProps) {
  const indicator = {
    live: '🟢',
    stale: '🟡',
    error: '🔴',
  }[state];

  const formatAge = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds}s ago`;
    }
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m ago`;
  };

  const stateLabel = {
    live: 'Live',
    stale: 'Stale',
    error: 'Error',
  }[state];

  return (
    <div className="flex items-center gap-2 text-sm text-gray-600">
      <span>{indicator}</span>
      <span>{stateLabel}</span>
      <span className="text-gray-400">({formatAge(ageSeconds)})</span>
      {lastUpdated && (
        <span className="text-gray-400">
          Last: {new Date(lastUpdated).toLocaleTimeString()}
        </span>
      )}
    </div>
  );
}
