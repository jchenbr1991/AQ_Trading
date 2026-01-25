// frontend/src/api/health.ts
import { apiClient } from './client';
import { SystemHealth } from '../types';

export async function fetchHealth(): Promise<SystemHealth> {
  const response = await apiClient.get<SystemHealth>('/health/detailed');
  return response.data;
}
