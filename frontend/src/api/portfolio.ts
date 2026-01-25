// frontend/src/api/portfolio.ts
import { apiClient } from './client';
import type { AccountSummary, Position } from '../types';

export async function fetchAccount(accountId: string): Promise<AccountSummary> {
  const response = await apiClient.get<AccountSummary>(`/portfolio/account/${accountId}`);
  return response.data;
}

export async function fetchPositions(accountId: string): Promise<Position[]> {
  const response = await apiClient.get<Position[]>(`/portfolio/positions/${accountId}`);
  return response.data;
}
