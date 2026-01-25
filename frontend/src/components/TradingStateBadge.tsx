// frontend/src/components/TradingStateBadge.tsx
import type { TradingStateValue } from '../types';

interface TradingStateBadgeProps {
  state: TradingStateValue;
}

export function TradingStateBadge({ state }: TradingStateBadgeProps) {
  const config = {
    RUNNING: {
      icon: '🟢',
      bg: 'bg-green-100 text-green-800',
      animate: false,
    },
    PAUSED: {
      icon: '🟡',
      bg: 'bg-yellow-100 text-yellow-800',
      animate: false,
    },
    HALTED: {
      icon: '🔴',
      bg: 'bg-red-100 text-red-800',
      animate: true,
    },
  }[state];

  return (
    <span
      className={`px-3 py-1 rounded-full font-medium ${config.bg} ${
        config.animate ? 'animate-pulse' : ''
      }`}
    >
      {config.icon} {state}
    </span>
  );
}
