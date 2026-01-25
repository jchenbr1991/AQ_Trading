// frontend/src/components/BacktestResults.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BacktestResults } from './BacktestResults';
import type { BacktestResult, EquityCurvePoint } from '../types';

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
});
