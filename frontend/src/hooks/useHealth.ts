// frontend/src/hooks/useHealth.ts
import { useQuery } from '@tanstack/react-query';
import { fetchHealth } from '../api/health';
import { SystemHealth } from '../types';

export function useHealth(refetchIntervalMs: number = 10000) {
  return useQuery<SystemHealth>({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: refetchIntervalMs,
  });
}
