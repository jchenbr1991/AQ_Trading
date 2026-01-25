// frontend/src/api/reconciliation.ts
import { apiClient } from './client';
import type { ReconciliationAlert } from '../types';

export async function fetchRecentAlerts(): Promise<ReconciliationAlert[]> {
  const response = await apiClient.get<ReconciliationAlert[]>('/reconciliation/recent');
  return response.data;
}
