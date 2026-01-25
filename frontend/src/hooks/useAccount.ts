import { useQuery } from '@tanstack/react-query';
import { fetchAccount } from '../api/portfolio';

export function useAccount(accountId: string) {
  return useQuery({
    queryKey: ['account', accountId],
    queryFn: () => fetchAccount(accountId),
  });
}
