// frontend/src/api/storage.ts
import { apiClient } from './client';
import { StorageStats } from '../types';

export async function fetchStorageStats(): Promise<StorageStats> {
  const response = await apiClient.get<StorageStats>('/storage');
  return response.data;
}
