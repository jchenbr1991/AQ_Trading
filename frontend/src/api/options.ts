// frontend/src/api/options.ts
/**
 * Options expiration API client.
 *
 * Endpoints:
 * - GET /options/expiring - List expiring option alerts
 * - POST /options/{position_id}/close - Close a position
 * - POST /options/alerts/{alert_id}/acknowledge - Acknowledge alert
 * - POST /options/check-expirations - Manual trigger
 */
import { apiClient } from './client';
import type {
  ExpiringAlertsResponse,
  OptionsClosePositionRequest,
  OptionsClosePositionResponse,
  AcknowledgeAlertResponse,
  ManualCheckResponse,
} from '../types';
import { v4 as uuidv4 } from 'uuid';

export type ExpiringAlertsStatus = 'pending' | 'acknowledged' | 'all';
export type ExpiringAlertsSortBy = 'dte' | 'severity' | 'expiry';

export interface FetchExpiringAlertsParams {
  accountId: string;
  status?: ExpiringAlertsStatus;
  sortBy?: ExpiringAlertsSortBy;
}

/**
 * Fetch expiring option alerts for an account.
 *
 * @param params - Query parameters
 * @returns List of expiring alerts with summary
 */
export async function fetchExpiringAlerts(
  params: FetchExpiringAlertsParams
): Promise<ExpiringAlertsResponse> {
  const response = await apiClient.get<ExpiringAlertsResponse>('/options/expiring', {
    params: {
      account_id: params.accountId,
      status: params.status ?? 'pending',
      sort_by: params.sortBy ?? 'dte',
    },
  });
  return response.data;
}

/**
 * Close an option position.
 *
 * Automatically generates an idempotency key to prevent duplicate orders.
 *
 * @param positionId - ID of the position to close
 * @param request - Close request with optional reason
 * @returns Close response with order ID
 */
export async function closePosition(
  positionId: number,
  request: OptionsClosePositionRequest = {}
): Promise<OptionsClosePositionResponse> {
  const idempotencyKey = uuidv4();

  const response = await apiClient.post<OptionsClosePositionResponse>(
    `/options/${positionId}/close`,
    request,
    {
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
    }
  );
  return response.data;
}

/**
 * Acknowledge an expiring alert.
 *
 * Marks the alert as acknowledged so it doesn't appear in pending list.
 *
 * @param alertId - ID of the alert to acknowledge
 * @returns Acknowledgment response
 */
export async function acknowledgeAlert(
  alertId: string
): Promise<AcknowledgeAlertResponse> {
  const response = await apiClient.post<AcknowledgeAlertResponse>(
    `/options/alerts/${alertId}/acknowledge`
  );
  return response.data;
}

/**
 * Manually trigger expiration check (for testing/internal use).
 *
 * @param accountId - Account to check
 * @returns Check statistics
 */
export async function triggerManualCheck(
  accountId: string
): Promise<ManualCheckResponse> {
  const response = await apiClient.post<ManualCheckResponse>(
    '/options/check-expirations',
    null,
    {
      params: { account_id: accountId },
    }
  );
  return response.data;
}
