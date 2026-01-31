// frontend/src/hooks/useDerivatives.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchExpiringPositions,
  fetchExpiringPositionsWithinDays,
  generateRollPlan,
} from '../api/derivatives';
import type { ExpiringPositionsResponse, RollPlanResponse } from '../types';

/**
 * Hook to fetch expiring derivative positions.
 *
 * @param days - Optional: number of days to look ahead. If not provided, uses default (5 days).
 * @param refetchIntervalMs - Refresh interval in ms (default: 30000)
 */
export function useExpiringPositions(
  days?: number,
  refetchIntervalMs: number = 30000
) {
  return useQuery<ExpiringPositionsResponse>({
    queryKey: ['derivatives', 'expiring', days],
    queryFn: () =>
      days !== undefined
        ? fetchExpiringPositionsWithinDays(days)
        : fetchExpiringPositions(),
    refetchInterval: refetchIntervalMs,
  });
}

/**
 * Hook to generate a roll plan for a futures position.
 *
 * Returns a mutation that can be triggered with a symbol.
 */
export function useGenerateRollPlan() {
  const queryClient = useQueryClient();

  return useMutation<RollPlanResponse, Error, string>({
    mutationFn: (symbol: string) => generateRollPlan(symbol),
    onSuccess: () => {
      // Invalidate expiring positions after roll plan is generated
      queryClient.invalidateQueries({ queryKey: ['derivatives', 'expiring'] });
    },
  });
}
