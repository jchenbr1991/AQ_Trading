// frontend/src/api/derivatives.ts
/**
 * Derivatives API client.
 *
 * Endpoints:
 * - GET /derivatives/expiring - List expiring derivative positions (default 5 days)
 * - GET /derivatives/expiring/{days} - Positions expiring within N days
 * - POST /derivatives/roll/{symbol} - Generate roll plan for futures
 */
import { apiClient } from './client';
import type {
  ExpiringPositionsResponse,
  RollPlanResponse,
} from '../types';

/**
 * Fetch expiring derivative positions using default warning window (5 days).
 *
 * @returns List of expiring positions
 */
export async function fetchExpiringPositions(): Promise<ExpiringPositionsResponse> {
  const response = await apiClient.get<ExpiringPositionsResponse>('/derivatives/expiring');
  return response.data;
}

/**
 * Fetch expiring derivative positions within N days.
 *
 * @param days - Number of days to look ahead (0-365)
 * @returns List of expiring positions
 */
export async function fetchExpiringPositionsWithinDays(
  days: number
): Promise<ExpiringPositionsResponse> {
  const response = await apiClient.get<ExpiringPositionsResponse>(
    `/derivatives/expiring/${days}`
  );
  return response.data;
}

/**
 * Generate a roll plan for a futures position.
 *
 * This generates instructions for rolling but does NOT execute trades.
 *
 * @param symbol - The futures contract symbol to roll (e.g., ESH24)
 * @returns Roll plan with close and open instructions
 */
export async function generateRollPlan(symbol: string): Promise<RollPlanResponse> {
  const response = await apiClient.post<RollPlanResponse>(
    `/derivatives/roll/${symbol}`
  );
  return response.data;
}
