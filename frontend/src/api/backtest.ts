// frontend/src/api/backtest.ts
import { apiClient } from './client';
import type { BacktestRequest, BacktestResponse } from '../types';

export async function runBacktest(request: BacktestRequest): Promise<BacktestResponse> {
  const response = await apiClient.post<BacktestResponse>('/backtest', request);
  return response.data;
}
