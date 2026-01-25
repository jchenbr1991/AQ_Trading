// frontend/src/hooks/useFreshness.ts
import { useState, useEffect } from 'react';
import type { FreshnessState } from '../types';

interface FreshnessResult {
  state: FreshnessState;
  ageSeconds: number;
  failureCount: number;
}

export function useFreshness(
  dataUpdatedAt: number | undefined,
  isError: boolean,
  failureCount: number
): FreshnessResult {
  const [ageSeconds, setAgeSeconds] = useState(0);

  useEffect(() => {
    const updateAge = () => {
      if (dataUpdatedAt) {
        setAgeSeconds(Math.floor((Date.now() - dataUpdatedAt) / 1000));
      }
    };

    updateAge();
    const interval = setInterval(updateAge, 1000);
    return () => clearInterval(interval);
  }, [dataUpdatedAt]);

  const calculateState = (): FreshnessState => {
    // Hard error: 3+ consecutive failures
    if (failureCount >= 3) {
      return 'error';
    }

    // No data yet
    if (!dataUpdatedAt) {
      return isError ? 'error' : 'stale';
    }

    // Calculate based on age
    if (ageSeconds < 10) {
      return 'live';
    } else if (ageSeconds < 30) {
      return 'stale';
    } else {
      return 'error';
    }
  };

  return {
    state: calculateState(),
    ageSeconds,
    failureCount,
  };
}
