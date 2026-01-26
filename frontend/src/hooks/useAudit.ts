// frontend/src/hooks/useAudit.ts
import { useQuery } from '@tanstack/react-query';
import { fetchAuditLogs, fetchAuditStats, fetchChainIntegrity } from '../api/audit';
import type { FetchAuditLogsParams } from '../api/audit';

export function useAuditLogs(params: FetchAuditLogsParams = {}) {
  return useQuery({
    queryKey: ['auditLogs', params],
    queryFn: () => fetchAuditLogs(params),
    refetchInterval: 30000, // 30 seconds
  });
}

export function useAuditStats() {
  return useQuery({
    queryKey: ['auditStats'],
    queryFn: fetchAuditStats,
    refetchInterval: 60000, // 1 minute
  });
}

export function useChainIntegrity(chainKey: string, limit?: number) {
  return useQuery({
    queryKey: ['chainIntegrity', chainKey, limit],
    queryFn: () => fetchChainIntegrity(chainKey, limit),
    enabled: !!chainKey,
  });
}
