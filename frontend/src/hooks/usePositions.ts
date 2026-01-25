import { useQuery } from '@tanstack/react-query';
import { fetchPositions } from '../api/portfolio';

export function usePositions(accountId: string) {
  return useQuery({
    queryKey: ['positions', accountId],
    queryFn: () => fetchPositions(accountId),
  });
}
