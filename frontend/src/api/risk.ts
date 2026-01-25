// frontend/src/api/risk.ts
import { apiClient } from './client';
import type { TradingState, KillSwitchResult } from '../types';

export async function fetchTradingState(): Promise<TradingState> {
  const response = await apiClient.get<TradingState>('/risk/state');
  return response.data;
}

export async function triggerKillSwitch(): Promise<KillSwitchResult> {
  const response = await apiClient.post<KillSwitchResult>('/risk/kill-switch');
  return response.data;
}

export async function pauseTrading(): Promise<void> {
  await apiClient.post('/risk/pause');
}

export async function resumeTrading(): Promise<void> {
  await apiClient.post('/risk/resume');
}
