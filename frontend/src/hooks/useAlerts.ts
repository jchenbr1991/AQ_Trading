import { useQuery } from '@tanstack/react-query';
import { fetchRecentAlerts } from '../api/reconciliation';

export function useAlerts() {
  return useQuery({
    queryKey: ['alerts'],
    queryFn: fetchRecentAlerts,
  });
}
