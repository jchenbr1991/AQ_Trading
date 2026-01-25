// frontend/src/pages/HealthPage.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HealthPage } from './HealthPage';
import * as useHealthModule from '../hooks/useHealth';

vi.mock('../hooks/useHealth');

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('HealthPage', () => {
  it('shows loading state', () => {
    vi.mocked(useHealthModule.useHealth).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as any);

    render(<HealthPage />, { wrapper: createWrapper() });

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('shows overall status when loaded', () => {
    vi.mocked(useHealthModule.useHealth).mockReturnValue({
      data: {
        overall_status: 'healthy',
        components: [
          {
            component: 'redis',
            status: 'healthy',
            latency_ms: 5.0,
            last_check: '2026-01-25T10:00:00Z',
            message: null,
          },
        ],
        checked_at: '2026-01-25T10:00:00Z',
      },
      isLoading: false,
      isError: false,
    } as any);

    render(<HealthPage />, { wrapper: createWrapper() });

    expect(screen.getByText('System Health')).toBeInTheDocument();
    expect(screen.getAllByText('healthy').length).toBeGreaterThan(0);
    expect(screen.getByText('redis')).toBeInTheDocument();
  });

  it('shows error state when fetch fails', () => {
    vi.mocked(useHealthModule.useHealth).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Network error'),
    } as any);

    render(<HealthPage />, { wrapper: createWrapper() });

    expect(screen.getByText(/error/i)).toBeInTheDocument();
  });

  it('renders all components', () => {
    vi.mocked(useHealthModule.useHealth).mockReturnValue({
      data: {
        overall_status: 'degraded',
        components: [
          {
            component: 'redis',
            status: 'healthy',
            latency_ms: 5.0,
            last_check: '2026-01-25T10:00:00Z',
            message: null,
          },
          {
            component: 'market_data',
            status: 'down',
            latency_ms: null,
            last_check: '2026-01-25T10:00:00Z',
            message: 'Connection refused',
          },
        ],
        checked_at: '2026-01-25T10:00:00Z',
      },
      isLoading: false,
      isError: false,
    } as any);

    render(<HealthPage />, { wrapper: createWrapper() });

    expect(screen.getByText('redis')).toBeInTheDocument();
    expect(screen.getByText('market_data')).toBeInTheDocument();
    expect(screen.getByText('Connection refused')).toBeInTheDocument();
  });
});
