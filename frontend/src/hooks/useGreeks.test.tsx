// frontend/src/hooks/useGreeks.test.tsx
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { useGreeksOverview } from './useGreeks';
import * as greeksApi from '../api/greeks';
import { ReactNode } from 'react';

vi.mock('../api/greeks');

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

describe('useGreeksOverview', () => {
  it('fetches Greeks overview', async () => {
    const mockData = {
      account: {
        scope: 'ACCOUNT' as const,
        scope_id: 'acc123',
        strategy_id: null,
        dollar_delta: 50000,
        gamma_dollar: 10000,
        gamma_pnl_1pct: 5000,
        vega_per_1pct: 20000,
        theta_per_day: -3000,
        coverage_pct: 100,
        is_coverage_sufficient: true,
        has_high_risk_missing_legs: false,
        valid_legs_count: 5,
        total_legs_count: 5,
        staleness_seconds: 0,
        as_of_ts: new Date().toISOString(),
      },
      strategies: {},
      alerts: [],
      top_contributors: {},
    };

    vi.mocked(greeksApi.fetchGreeksOverview).mockResolvedValue(mockData);

    const { result } = renderHook(() => useGreeksOverview('acc123', 0), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockData);
  });
});
