// frontend/src/api/orders.ts
import { apiClient } from './client';
import type { ClosePositionRequest } from '../types';

export async function closePosition(request: ClosePositionRequest): Promise<{ success: boolean; order_id: string }> {
  const response = await apiClient.post('/orders/close', request);
  return response.data;
}
