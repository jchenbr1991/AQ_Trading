// frontend/src/hooks/useBacktest.ts
import { useMutation } from '@tanstack/react-query';
import { runBacktest } from '../api/backtest';
import type { BacktestRequest, BacktestResponse } from '../types';

export function useBacktest() {
  return useMutation<BacktestResponse, Error, BacktestRequest>({
    mutationFn: runBacktest,
  });
}
