// frontend/src/api/alerts.ts
import { apiClient } from './client';
import type { AlertListResponse, AlertStats, AlertDelivery } from '../types';

export interface FetchAlertsParams {
  severity?: number;
  type?: string;
  limit?: number;
  offset?: number;
}

export async function fetchAlerts(params: FetchAlertsParams = {}): Promise<AlertListResponse> {
  const response = await apiClient.get<AlertListResponse>('/alerts', { params });
  return response.data;
}

export async function fetchAlertStats(): Promise<AlertStats> {
  const response = await apiClient.get<AlertStats>('/alerts/stats');
  return response.data;
}

export async function fetchAlertDeliveries(alertId: string): Promise<AlertDelivery[]> {
  const response = await apiClient.get<AlertDelivery[]>(`/alerts/${alertId}/deliveries`);
  return response.data;
}
