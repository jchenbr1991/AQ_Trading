// frontend/src/hooks/useAlerts.ts
import { useQuery } from '@tanstack/react-query';
import { fetchAlerts, fetchAlertStats, fetchAlertDeliveries } from '../api/alerts';
import type { FetchAlertsParams } from '../api/alerts';

export function useAlerts(params: FetchAlertsParams = {}) {
  return useQuery({
    queryKey: ['alerts', params],
    queryFn: () => fetchAlerts(params),
    refetchInterval: 30000, // 30 seconds
  });
}

export function useAlertStats() {
  return useQuery({
    queryKey: ['alertStats'],
    queryFn: fetchAlertStats,
    refetchInterval: 60000, // 1 minute
  });
}

export function useAlertDeliveries(alertId: string) {
  return useQuery({
    queryKey: ['alertDeliveries', alertId],
    queryFn: () => fetchAlertDeliveries(alertId),
    enabled: !!alertId,
  });
}
