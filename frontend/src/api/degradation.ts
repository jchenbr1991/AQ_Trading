// frontend/src/api/degradation.ts
import { apiClient } from './client';
import type {
  SystemStatus,
  TradingPermissions,
  ForceOverrideRequest,
  ForceOverrideResponse,
} from '../types';

/**
 * Fetch current system degradation status.
 * Returns the current mode, recovery stage, and override information.
 */
export async function fetchSystemStatus(): Promise<SystemStatus> {
  const response = await apiClient.get<SystemStatus>('/degradation/status');
  return response.data;
}

/**
 * Fetch current trading permissions for all action types.
 * Returns permissions based on the current system mode and recovery stage.
 */
export async function fetchTradingPermissions(): Promise<TradingPermissions> {
  const response = await apiClient.get<TradingPermissions>('/degradation/permissions');
  return response.data;
}

/**
 * Force the system into a specific mode (manual intervention).
 * The override is temporary and will expire after the specified TTL.
 */
export async function forceSystemMode(request: ForceOverrideRequest): Promise<ForceOverrideResponse> {
  const response = await apiClient.post<ForceOverrideResponse>('/degradation/force', request);
  return response.data;
}
