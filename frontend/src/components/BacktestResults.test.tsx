// frontend/src/components/BacktestResults.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BacktestResults } from './BacktestResults';
import type { BacktestResult, EquityCurvePoint, SignalTrace } from '../types';

// Mock recharts to avoid rendering issues in tests
vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => <div data-testid="line-chart">{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// Helper to create a minimal valid trace
function createTrace(overrides: Partial<SignalTrace> = {}): SignalTrace {
  return {
    trace_id: 'trace-1',
    signal_timestamp: '2024-01-15T10:30:00Z',
    symbol: 'AAPL',
    signal_direction: 'buy',
    signal_quantity: 100,
    signal_reason: null,
    signal_bar: {
      symbol: 'AAPL',
      timestamp: '2024-01-15T10:30:00Z',
      open: '150.00',
      high: '151.00',
      low: '149.00',
      close: '150.50',
      volume: 1000000,
    },
    portfolio_state: {
      cash: '100000.00',
      position_qty: 0,
      position_avg_cost: null,
      equity: '100000.00',
    },
    strategy_snapshot: null,
    fill_bar: null,
    fill_timestamp: null,
    fill_quantity: null,
    fill_price: null,
    expected_price: null,
    expected_price_type: null,
    slippage: null,
    slippage_bps: null,
    commission: null,
    ...overrides,
  };
}

describe('BacktestResults', () => {
  const mockResult: BacktestResult = {
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
    benchmark: null,
    traces: [],
  };

  it('renders total return prominently', () => {
    render(<BacktestResults result={mockResult} />);

    expect(screen.getByText('+5.00%')).toBeInTheDocument();
    expect(screen.getByText('Total Return')).toBeInTheDocument();
  });

  it('renders all key metrics', () => {
    render(<BacktestResults result={mockResult} />);

    expect(screen.getByText('Final Equity')).toBeInTheDocument();
    expect(screen.getByText('$105,000.00')).toBeInTheDocument();

    expect(screen.getByText('Final Cash')).toBeInTheDocument();
    expect(screen.getByText('$5,000.00')).toBeInTheDocument();

    expect(screen.getByText('Final Position')).toBeInTheDocument();
    expect(screen.getByText('100 shares')).toBeInTheDocument();

    expect(screen.getByText('Sharpe Ratio')).toBeInTheDocument();
    expect(screen.getByText('1.25')).toBeInTheDocument();

    expect(screen.getByText('Total Trades')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();

    expect(screen.getByText('Avg Trade P&L')).toBeInTheDocument();
    expect(screen.getByText('$250.00')).toBeInTheDocument();
  });

  it('renders warm-up information', () => {
    render(<BacktestResults result={mockResult} />);

    expect(screen.getByText(/warm-up period/i)).toBeInTheDocument();
    expect(screen.getByText(/20 of 20 required bars/i)).toBeInTheDocument();
  });

  it('shows negative returns in red', () => {
    const negativeResult: BacktestResult = {
      ...mockResult,
      total_return: '-0.10',
    };

    render(<BacktestResults result={negativeResult} />);

    const returnElement = screen.getByText('-10.00%');
    expect(returnElement).toHaveClass('text-red-600');
  });

  it('shows positive returns in green', () => {
    render(<BacktestResults result={mockResult} />);

    const returnElement = screen.getByText('+5.00%');
    expect(returnElement).toHaveClass('text-green-600');
  });

  it('renders equity chart when data provided', () => {
    const equityCurve: EquityCurvePoint[] = [
      { timestamp: '2024-01-01T00:00:00Z', equity: 100000 },
      { timestamp: '2024-01-02T00:00:00Z', equity: 101000 },
    ];

    render(<BacktestResults result={mockResult} equityCurve={equityCurve} />);

    expect(screen.getByText('Equity Curve')).toBeInTheDocument();
  });

  it('does not render equity chart when no data', () => {
    render(<BacktestResults result={mockResult} equityCurve={[]} />);

    expect(screen.queryByText('Equity Curve')).not.toBeInTheDocument();
  });

  it('displays benchmark comparison when available', () => {
    const resultWithBenchmark: BacktestResult = {
      ...mockResult,
      benchmark: {
        benchmark_symbol: 'SPY',
        benchmark_total_return: '0.10',
        alpha: '0.05',
        beta: '0.8',
        tracking_error: '0.02',
        information_ratio: '2.5',
        sortino_ratio: '1.8',
        up_capture: '1.1',
        down_capture: '0.9',
      },
    };

    render(<BacktestResults result={resultWithBenchmark} />);

    expect(screen.getByText('vs SPY')).toBeInTheDocument();
    expect(screen.getByText('Alpha (Ann.)')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
    expect(screen.getByText('0.80')).toBeInTheDocument(); // beta formatted
  });

  it('does not display benchmark section when benchmark is null', () => {
    render(<BacktestResults result={mockResult} />);

    expect(screen.queryByText(/vs SPY/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Alpha (Ann.)')).not.toBeInTheDocument();
  });

  it('displays slippage stats with traces', () => {
    const resultWithTraces: BacktestResult = {
      ...mockResult,
      traces: [
        createTrace({
          trace_id: 'trace-1',
          fill_price: '150.25',
          fill_quantity: 100,
          slippage: '0.25',
          slippage_bps: '17',
        }),
      ],
    };

    render(<BacktestResults result={resultWithTraces} />);

    expect(screen.getByText('Execution Quality')).toBeInTheDocument();
    expect(screen.getByText('Total Slippage')).toBeInTheDocument();
    expect(screen.getByText('Avg Slippage (bps)')).toBeInTheDocument();
  });

  it('displays trace table with traces', () => {
    const resultWithTraces: BacktestResult = {
      ...mockResult,
      traces: [
        createTrace({
          trace_id: 'trace-1',
          symbol: 'AAPL',
          signal_direction: 'buy',
          signal_quantity: 100,
          expected_price: '150.00',
          fill_price: '150.25',
          slippage_bps: '17',
        }),
      ],
    };

    render(<BacktestResults result={resultWithTraces} />);

    expect(screen.getByText('Trade Details')).toBeInTheDocument();
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByText('BUY')).toBeInTheDocument();
    expect(screen.getByText('$150.00')).toBeInTheDocument();
    expect(screen.getByText('$150.25')).toBeInTheDocument();
  });

  it('hides slippage stats when no traces', () => {
    render(<BacktestResults result={mockResult} />);

    // SlippageStats returns null when no traces
    expect(screen.queryByText('Execution Quality')).not.toBeInTheDocument();
    // TraceTable still shows but with empty state message
    expect(screen.getByText('Trade Details')).toBeInTheDocument();
    expect(screen.getByText('No trades executed')).toBeInTheDocument();
  });
});
