// frontend/src/pages/BacktestPage.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BacktestPage } from './BacktestPage';
import * as useBacktestModule from '../hooks/useBacktest';

vi.mock('../hooks/useBacktest');

// Mock recharts to avoid rendering issues in tests
vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => <div data-testid="line-chart">{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('BacktestPage', () => {
  const mockMutate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders page header', () => {
    vi.mocked(useBacktestModule.useBacktest).mockReturnValue({
      mutate: mockMutate,
      data: undefined,
      isPending: false,
      isError: false,
      error: null,
    } as any);

    render(<BacktestPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Backtest')).toBeInTheDocument();
    expect(screen.getByText(/test your strategy/i)).toBeInTheDocument();
  });

  it('renders backtest form', () => {
    vi.mocked(useBacktestModule.useBacktest).mockReturnValue({
      mutate: mockMutate,
      data: undefined,
      isPending: false,
      isError: false,
      error: null,
    } as any);

    render(<BacktestPage />, { wrapper: createWrapper() });

    expect(screen.getByLabelText(/symbol/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run backtest/i })).toBeInTheDocument();
  });

  it('shows loading state while backtest is running', () => {
    vi.mocked(useBacktestModule.useBacktest).mockReturnValue({
      mutate: mockMutate,
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    } as any);

    render(<BacktestPage />, { wrapper: createWrapper() });

    expect(screen.getByRole('button', { name: /running backtest/i })).toBeDisabled();
  });

  it('shows error when backtest fails with network error', () => {
    vi.mocked(useBacktestModule.useBacktest).mockReturnValue({
      mutate: mockMutate,
      data: undefined,
      isPending: false,
      isError: true,
      error: new Error('Network error'),
    } as any);

    render(<BacktestPage />, { wrapper: createWrapper() });

    expect(screen.getByText(/error running backtest/i)).toBeInTheDocument();
    expect(screen.getByText(/network error/i)).toBeInTheDocument();
  });

  it('shows error when backtest status is failed', () => {
    vi.mocked(useBacktestModule.useBacktest).mockReturnValue({
      mutate: mockMutate,
      data: {
        backtest_id: 'bt-123',
        status: 'failed',
        result: null,
        error: 'Invalid date range',
      },
      isPending: false,
      isError: false,
      error: null,
    } as any);

    render(<BacktestPage />, { wrapper: createWrapper() });

    expect(screen.getByText(/backtest failed/i)).toBeInTheDocument();
    expect(screen.getByText(/invalid date range/i)).toBeInTheDocument();
  });

  it('shows results when backtest completes successfully', () => {
    vi.mocked(useBacktestModule.useBacktest).mockReturnValue({
      mutate: mockMutate,
      data: {
        backtest_id: 'bt-123',
        status: 'completed',
        result: {
          final_equity: '105000.00',
          final_cash: '5000.00',
          final_position_qty: 100,
          total_return: '0.05',
          annualized_return: '0.06',
          sharpe_ratio: '1.25',
          max_drawdown: '-0.08',
          win_rate: '0.55',
          total_trades: 20,
          avg_trade_pnl: '250.00',
          warm_up_required_bars: 20,
          warm_up_bars_used: 20,
        },
        error: null,
      },
      isPending: false,
      isError: false,
      error: null,
    } as any);

    render(<BacktestPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Backtest Results')).toBeInTheDocument();
    // Check that total return is displayed (it shows both in header and metrics grid, so use getAllByText)
    expect(screen.getAllByText('+5.00%').length).toBeGreaterThan(0);
    expect(screen.getByText('$105,000.00')).toBeInTheDocument();
  });

  it('calls mutate when form is submitted', () => {
    vi.mocked(useBacktestModule.useBacktest).mockReturnValue({
      mutate: mockMutate,
      data: undefined,
      isPending: false,
      isError: false,
      error: null,
    } as any);

    render(<BacktestPage />, { wrapper: createWrapper() });

    fireEvent.click(screen.getByRole('button', { name: /run backtest/i }));

    expect(mockMutate).toHaveBeenCalled();
  });
});
