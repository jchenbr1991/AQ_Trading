// frontend/src/api/greeks.ts
import { apiClient } from './client';
import type { GreeksOverview, AggregatedGreeks, GreeksAlert } from '../types';

export async function fetchGreeksOverview(accountId: string): Promise<GreeksOverview> {
  const response = await apiClient.get<GreeksOverview>(`/greeks/accounts/${accountId}`);
  return response.data;
}

export async function fetchCurrentGreeks(accountId: string): Promise<AggregatedGreeks> {
  const response = await apiClient.get<AggregatedGreeks>(`/greeks/accounts/${accountId}/current`);
  return response.data;
}

export async function fetchGreeksAlerts(
  accountId: string,
  acknowledged?: boolean,
): Promise<GreeksAlert[]> {
  const params = acknowledged !== undefined ? { acknowledged } : {};
  const response = await apiClient.get<GreeksAlert[]>(
    `/greeks/accounts/${accountId}/alerts`,
    { params },
  );
  return response.data;
}

export async function acknowledgeGreeksAlert(
  alertId: string,
  acknowledgedBy: string,
): Promise<GreeksAlert> {
  const response = await apiClient.post<GreeksAlert>(
    `/greeks/alerts/${alertId}/acknowledge`,
    { acknowledged_by: acknowledgedBy },
  );
  return response.data;
}
