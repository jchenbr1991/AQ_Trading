// frontend/src/components/TraceTable.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TraceTable } from './TraceTable';
import type { SignalTrace } from '../types';

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

describe('TraceTable', () => {
  it('renders empty state when no traces', () => {
    render(<TraceTable traces={[]} />);

    expect(screen.getByText('No trades executed')).toBeInTheDocument();
  });

  it('renders table with traces', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        symbol: 'AAPL',
        signal_direction: 'buy',
        signal_quantity: 100,
        expected_price: '150.00',
        fill_price: '150.25',
        slippage_bps: '17',
      }),
      createTrace({
        trace_id: 'trace-2',
        symbol: 'GOOGL',
        signal_direction: 'sell',
        signal_quantity: 50,
        expected_price: '140.00',
        fill_price: '139.80',
        slippage_bps: '-14',
      }),
    ];

    render(<TraceTable traces={traces} />);

    // Check headers
    expect(screen.getByText('Time')).toBeInTheDocument();
    expect(screen.getByText('Symbol')).toBeInTheDocument();
    expect(screen.getByText('Side')).toBeInTheDocument();
    expect(screen.getByText('Qty')).toBeInTheDocument();
    expect(screen.getByText('Expected')).toBeInTheDocument();
    expect(screen.getByText('Fill')).toBeInTheDocument();
    expect(screen.getByText('Slippage (bps)')).toBeInTheDocument();

    // Check data rows
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByText('GOOGL')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
  });

  it('displays buy in green, sell in red', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        signal_direction: 'buy',
      }),
      createTrace({
        trace_id: 'trace-2',
        signal_direction: 'sell',
      }),
    ];

    render(<TraceTable traces={traces} />);

    const buyElement = screen.getByText('BUY');
    const sellElement = screen.getByText('SELL');

    expect(buyElement).toHaveClass('text-green-600');
    expect(sellElement).toHaveClass('text-red-600');
  });

  it('formats slippage with color (positive=red, negative=green)', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        slippage_bps: '25', // Unfavorable (paid more)
      }),
      createTrace({
        trace_id: 'trace-2',
        slippage_bps: '-15', // Favorable (paid less)
      }),
    ];

    render(<TraceTable traces={traces} />);

    const positiveSlippage = screen.getByText('+25');
    const negativeSlippage = screen.getByText('-15');

    expect(positiveSlippage).toHaveClass('text-red-600');
    expect(negativeSlippage).toHaveClass('text-green-600');
  });

  it('handles null fill data gracefully', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        expected_price: null,
        fill_price: null,
        slippage_bps: null,
      }),
    ];

    render(<TraceTable traces={traces} />);

    // Should show dashes for null values
    const dashes = screen.getAllByText('-');
    expect(dashes.length).toBe(3); // expected, fill, slippage
  });

  it('formats prices correctly', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        expected_price: '150.00',
        fill_price: '150.25',
      }),
    ];

    render(<TraceTable traces={traces} />);

    expect(screen.getByText('$150.00')).toBeInTheDocument();
    expect(screen.getByText('$150.25')).toBeInTheDocument();
  });

  it('formats timestamp as date', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        signal_timestamp: '2024-01-15T10:30:00Z',
      }),
    ];

    render(<TraceTable traces={traces} />);

    // The exact format depends on locale, but should contain date parts
    // Using a flexible check that works across locales
    const dateCell = screen.getByText(/1\/15\/2024|15\/1\/2024|2024/);
    expect(dateCell).toBeInTheDocument();
  });
});
