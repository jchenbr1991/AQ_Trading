// frontend/src/api/audit.ts
import { apiClient } from './client';
import type { AuditLogListResponse, AuditStats, ChainIntegrity } from '../types';

export interface FetchAuditLogsParams {
  event_type?: string;
  resource_type?: string;
  resource_id?: string;
  actor_id?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
  offset?: number;
}

export async function fetchAuditLogs(params: FetchAuditLogsParams = {}): Promise<AuditLogListResponse> {
  const response = await apiClient.get<AuditLogListResponse>('/audit', { params });
  return response.data;
}

export async function fetchAuditStats(): Promise<AuditStats> {
  const response = await apiClient.get<AuditStats>('/audit/stats');
  return response.data;
}

export async function fetchChainIntegrity(chainKey: string, limit?: number): Promise<ChainIntegrity> {
  const params = limit !== undefined ? { limit } : undefined;
  const response = await apiClient.get<ChainIntegrity>(`/audit/integrity/${encodeURIComponent(chainKey)}`, { params });
  return response.data;
}
