// frontend/src/hooks/useDegradation.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchSystemStatus, fetchTradingPermissions, forceSystemMode } from '../api/degradation';
import type { SystemStatus, TradingPermissions, ForceOverrideRequest, ForceOverrideResponse } from '../types';

export function useSystemStatus(refetchIntervalMs: number = 5000) {
  return useQuery<SystemStatus>({
    queryKey: ['systemStatus'],
    queryFn: fetchSystemStatus,
    refetchInterval: refetchIntervalMs,
  });
}

export function useTradingPermissions(refetchIntervalMs: number = 5000) {
  return useQuery<TradingPermissions>({
    queryKey: ['tradingPermissions'],
    queryFn: fetchTradingPermissions,
    refetchInterval: refetchIntervalMs,
  });
}

export function useForceSystemMode() {
  const queryClient = useQueryClient();

  return useMutation<ForceOverrideResponse, Error, ForceOverrideRequest>({
    mutationFn: forceSystemMode,
    onSuccess: () => {
      // Invalidate queries to refetch latest state
      queryClient.invalidateQueries({ queryKey: ['systemStatus'] });
      queryClient.invalidateQueries({ queryKey: ['tradingPermissions'] });
    },
  });
}
