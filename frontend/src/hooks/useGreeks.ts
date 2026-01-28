// frontend/src/hooks/useGreeks.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchGreeksOverview,
  fetchCurrentGreeks,
  fetchGreeksAlerts,
  acknowledgeGreeksAlert,
} from '../api/greeks';
import type { GreeksOverview, AggregatedGreeks, GreeksAlert } from '../types';

export function useGreeksOverview(accountId: string, refetchInterval = 5000) {
  return useQuery<GreeksOverview>({
    queryKey: ['greeks', 'overview', accountId],
    queryFn: () => fetchGreeksOverview(accountId),
    refetchInterval,
    staleTime: 2000,
  });
}

export function useCurrentGreeks(accountId: string, refetchInterval = 5000) {
  return useQuery<AggregatedGreeks>({
    queryKey: ['greeks', 'current', accountId],
    queryFn: () => fetchCurrentGreeks(accountId),
    refetchInterval,
    staleTime: 2000,
  });
}

export function useGreeksAlerts(accountId: string, acknowledged?: boolean) {
  return useQuery<GreeksAlert[]>({
    queryKey: ['greeks', 'alerts', accountId, acknowledged],
    queryFn: () => fetchGreeksAlerts(accountId, acknowledged),
    refetchInterval: 10000,
  });
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ alertId, acknowledgedBy }: { alertId: string; acknowledgedBy: string }) =>
      acknowledgeGreeksAlert(alertId, acknowledgedBy),
    onSuccess: () => {
      // Invalidate alerts query to refetch
      queryClient.invalidateQueries({ queryKey: ['greeks', 'alerts'] });
    },
  });
}
