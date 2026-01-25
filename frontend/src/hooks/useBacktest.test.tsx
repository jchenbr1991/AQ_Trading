// frontend/src/hooks/useBacktest.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useBacktest } from './useBacktest';
import * as backtestApi from '../api/backtest';

vi.mock('../api/backtest');

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('useBacktest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockRequest = {
    strategy_class: 'MeanReversionStrategy',
    strategy_params: { lookback_period: 20, threshold: 2.0, position_size: 100 },
    symbol: 'AAPL',
    start_date: '2024-01-01',
    end_date: '2024-12-31',
    initial_capital: '100000',
    slippage_bps: 5,
  };

  const mockResponse = {
    backtest_id: 'bt-123',
    status: 'completed' as const,
    result: {
      final_equity: '105000.00',
      final_cash: '5000.00',
      final_position_qty: 100,
      total_return: '0.05',
      annualized_return: '0.05',
      sharpe_ratio: '1.25',
      max_drawdown: '0.08',
      win_rate: '0.55',
      total_trades: 20,
      avg_trade_pnl: '250.00',
      warm_up_required_bars: 20,
      warm_up_bars_used: 20,
      benchmark: null,
    },
    error: null,
  };

  it('starts in idle state', () => {
    const { result } = renderHook(() => useBacktest(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isPending).toBe(false);
    expect(result.current.isSuccess).toBe(false);
    expect(result.current.data).toBeUndefined();
  });

  it('runs backtest mutation successfully', async () => {
    vi.mocked(backtestApi.runBacktest).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBacktest(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate(mockRequest);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockResponse);
    expect(backtestApi.runBacktest).toHaveBeenCalled();
    // Verify the request object was passed (first argument)
    expect(vi.mocked(backtestApi.runBacktest).mock.calls[0][0]).toEqual(mockRequest);
  });

  it('handles mutation error', async () => {
    const error = new Error('Network error');
    vi.mocked(backtestApi.runBacktest).mockRejectedValue(error);

    const { result } = renderHook(() => useBacktest(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate(mockRequest);
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toEqual(error);
  });

  it('shows pending state while running', async () => {
    vi.mocked(backtestApi.runBacktest).mockImplementation(
      () => new Promise(() => {})
    );

    const { result } = renderHook(() => useBacktest(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate(mockRequest);
    });

    await waitFor(() => {
      expect(result.current.isPending).toBe(true);
    });
  });
});
