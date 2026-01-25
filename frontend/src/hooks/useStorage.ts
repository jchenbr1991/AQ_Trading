// frontend/src/hooks/useStorage.ts
import { useQuery } from '@tanstack/react-query';
import { fetchStorageStats } from '../api/storage';
import type { StorageStats } from '../types';

export function useStorage() {
  return useQuery<StorageStats>({
    queryKey: ['storage'],
    queryFn: fetchStorageStats,
    refetchInterval: 30000, // Refresh every 30 seconds
  });
}
