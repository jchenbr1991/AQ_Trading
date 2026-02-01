// frontend/src/hooks/useAgents.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  invokeAgent,
  fetchAgentResults,
  fetchAgentResult,
} from '../api/agents';
import type {
  AgentInvokeRequest,
  AgentResultResponse,
  AgentResultsListResponse,
} from '../types';

/**
 * Hook to fetch agent results history.
 *
 * @param limit - Number of results to fetch (default: 20)
 * @param offset - Offset for pagination (default: 0)
 * @param refetchIntervalMs - Refresh interval in ms (default: 30000)
 */
export function useAgentResults(
  limit: number = 20,
  offset: number = 0,
  refetchIntervalMs: number = 30000
) {
  return useQuery<AgentResultsListResponse>({
    queryKey: ['agents', 'results', limit, offset],
    queryFn: () => fetchAgentResults(limit, offset),
    refetchInterval: refetchIntervalMs,
  });
}

/**
 * Hook to fetch a specific agent result.
 *
 * @param id - The result ID
 */
export function useAgentResult(id: string) {
  return useQuery<AgentResultResponse>({
    queryKey: ['agents', 'results', id],
    queryFn: () => fetchAgentResult(id),
    enabled: !!id,
  });
}

/**
 * Hook to invoke an agent task.
 *
 * Returns a mutation that can be triggered with an AgentInvokeRequest.
 */
export function useInvokeAgent() {
  const queryClient = useQueryClient();

  return useMutation<AgentResultResponse, Error, AgentInvokeRequest>({
    mutationFn: (request: AgentInvokeRequest) => invokeAgent(request),
    onSuccess: () => {
      // Invalidate results list after invoking a new agent task
      queryClient.invalidateQueries({ queryKey: ['agents', 'results'] });
    },
  });
}
