// frontend/src/api/agents.ts
import { apiClient } from './client';
import type {
  AgentInvokeRequest,
  AgentResultResponse,
  AgentResultsListResponse,
} from '../types';

export async function invokeAgent(
  request: AgentInvokeRequest
): Promise<AgentResultResponse> {
  const response = await apiClient.post<AgentResultResponse>(
    '/agents/invoke',
    request
  );
  return response.data;
}

export async function fetchAgentResults(
  limit: number = 20,
  offset: number = 0
): Promise<AgentResultsListResponse> {
  const response = await apiClient.get<AgentResultsListResponse>(
    '/agents/results',
    {
      params: { limit, offset },
    }
  );
  return response.data;
}

export async function fetchAgentResult(id: string): Promise<AgentResultResponse> {
  const response = await apiClient.get<AgentResultResponse>(
    `/agents/results/${id}`
  );
  return response.data;
}
