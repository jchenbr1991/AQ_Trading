// frontend/src/hooks/useHealth.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useHealth } from './useHealth';
import * as healthApi from '../api/health';

vi.mock('../api/health');

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

describe('useHealth', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches health data on mount', async () => {
    const mockHealth = {
      overall_status: 'healthy' as const,
      components: [
        {
          component: 'redis',
          status: 'healthy' as const,
          latency_ms: 5.0,
          last_check: '2026-01-25T10:00:00Z',
          message: null,
        },
      ],
      checked_at: '2026-01-25T10:00:00Z',
    };

    vi.mocked(healthApi.fetchHealth).mockResolvedValue(mockHealth);

    const { result } = renderHook(() => useHealth(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockHealth);
    expect(healthApi.fetchHealth).toHaveBeenCalledTimes(1);
  });

  it('returns loading state initially', () => {
    vi.mocked(healthApi.fetchHealth).mockImplementation(
      () => new Promise(() => {})
    );

    const { result } = renderHook(() => useHealth(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
  });

  it('accepts custom refetch interval', async () => {
    const mockHealth = {
      overall_status: 'healthy' as const,
      components: [],
      checked_at: '2026-01-25T10:00:00Z',
    };

    vi.mocked(healthApi.fetchHealth).mockResolvedValue(mockHealth);

    // Test that the hook accepts a custom interval parameter
    const customInterval = 5000;
    const { result } = renderHook(() => useHealth(customInterval), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockHealth);
  });
});
