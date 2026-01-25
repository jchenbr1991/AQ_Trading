// frontend/src/hooks/useStorage.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useStorage } from './useStorage';
import * as api from '../api/storage';
import type { ReactNode } from 'react';

vi.mock('../api/storage');

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('useStorage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns storage stats on success', async () => {
    const mockStats = {
      database_size_bytes: 1000000,
      database_size_pretty: '1 MB',
      timestamp: '2026-01-25T00:00:00Z',
      tables: [
        {
          table_name: 'transactions',
          row_count: 100,
          size_bytes: 500000,
          size_pretty: '500 KB',
          is_hypertable: true,
        },
      ],
      compression: {},
    };

    vi.mocked(api.fetchStorageStats).mockResolvedValue(mockStats);

    const { result } = renderHook(() => useStorage(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockStats);
  });

  it('returns error on failure', async () => {
    vi.mocked(api.fetchStorageStats).mockRejectedValue(new Error('Failed'));

    const { result } = renderHook(() => useStorage(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });

  it('returns loading state initially', () => {
    vi.mocked(api.fetchStorageStats).mockImplementation(
      () => new Promise(() => {})
    );

    const { result } = renderHook(() => useStorage(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
  });
});
