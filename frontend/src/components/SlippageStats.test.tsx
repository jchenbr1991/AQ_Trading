// frontend/src/components/SlippageStats.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SlippageStats } from './SlippageStats';
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

describe('SlippageStats', () => {
  it('returns null when no traces', () => {
    const { container } = render(<SlippageStats traces={[]} />);

    expect(container.firstChild).toBeNull();
  });

  it('displays stats for filled traces', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        fill_price: '150.25',
        fill_quantity: 100,
        slippage: '0.25',
        slippage_bps: '17',
      }),
    ];

    render(<SlippageStats traces={traces} />);

    expect(screen.getByText('Execution Quality')).toBeInTheDocument();
    expect(screen.getByText('Total Slippage')).toBeInTheDocument();
    expect(screen.getByText('Avg Slippage (bps)')).toBeInTheDocument();
    expect(screen.getByText('Worst Slippage (bps)')).toBeInTheDocument();
    expect(screen.getByText('Unfavorable Fills')).toBeInTheDocument();
  });

  it('calculates total slippage in dollars', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        fill_price: '150.25',
        fill_quantity: 100,
        slippage: '0.25', // $0.25 per share * 100 shares = $25
        slippage_bps: '17',
      }),
      createTrace({
        trace_id: 'trace-2',
        fill_price: '200.50',
        fill_quantity: 50,
        slippage: '0.10', // $0.10 per share * 50 shares = $5
        slippage_bps: '5',
      }),
    ];

    render(<SlippageStats traces={traces} />);

    // Total: $25 + $5 = $30.00
    expect(screen.getByText('$30.00')).toBeInTheDocument();
  });

  it('calculates average slippage in bps', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        fill_price: '150.25',
        fill_quantity: 100,
        slippage: '0.25',
        slippage_bps: '20',
      }),
      createTrace({
        trace_id: 'trace-2',
        fill_price: '200.50',
        fill_quantity: 50,
        slippage: '0.10',
        slippage_bps: '10',
      }),
    ];

    render(<SlippageStats traces={traces} />);

    // Average: (20 + 10) / 2 = 15.0
    expect(screen.getByText('+15.0')).toBeInTheDocument();
  });

  it('shows worst slippage', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        fill_price: '150.25',
        fill_quantity: 100,
        slippage: '0.25',
        slippage_bps: '10',
      }),
      createTrace({
        trace_id: 'trace-2',
        fill_price: '200.50',
        fill_quantity: 50,
        slippage: '0.50',
        slippage_bps: '35', // Worst
      }),
      createTrace({
        trace_id: 'trace-3',
        fill_price: '100.00',
        fill_quantity: 25,
        slippage: '-0.10',
        slippage_bps: '-5', // Favorable
      }),
    ];

    render(<SlippageStats traces={traces} />);

    // Worst slippage (highest positive): 35.0
    expect(screen.getByText('+35.0')).toBeInTheDocument();
  });

  it('shows unfavorable fill percentage', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        fill_price: '150.25',
        fill_quantity: 100,
        slippage: '0.25',
        slippage_bps: '17', // Unfavorable (positive)
      }),
      createTrace({
        trace_id: 'trace-2',
        fill_price: '200.50',
        fill_quantity: 50,
        slippage: '-0.10',
        slippage_bps: '-5', // Favorable (negative)
      }),
      createTrace({
        trace_id: 'trace-3',
        fill_price: '100.00',
        fill_quantity: 25,
        slippage: '0.05',
        slippage_bps: '5', // Unfavorable (positive)
      }),
    ];

    render(<SlippageStats traces={traces} />);

    // 2 out of 3 unfavorable = 67%
    expect(screen.getByText('67%')).toBeInTheDocument();
  });

  it('handles traces with null slippage', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        fill_price: '150.25',
        fill_quantity: 100,
        slippage: '0.25',
        slippage_bps: '17',
      }),
      createTrace({
        trace_id: 'trace-2',
        // No fill data - should be excluded from calculations
        fill_price: null,
        fill_quantity: null,
        slippage: null,
        slippage_bps: null,
      }),
    ];

    render(<SlippageStats traces={traces} />);

    // Only the first trace should be counted
    // Total slippage: $0.25 * 100 = $25.00
    expect(screen.getByText('$25.00')).toBeInTheDocument();
    // Average and worst are same when single trace: 17.0 bps
    const bpsElements = screen.getAllByText('+17.0');
    expect(bpsElements).toHaveLength(2); // avg and worst
    // 100% unfavorable (1 out of 1 filled trace)
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('shows negative values in green for favorable slippage', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        fill_price: '149.75',
        fill_quantity: 100,
        slippage: '-0.25', // Favorable - paid less
        slippage_bps: '-17',
      }),
    ];

    render(<SlippageStats traces={traces} />);

    // Total slippage: -$25.00 (favorable)
    const totalSlippage = screen.getByText('$-25.00');
    expect(totalSlippage).toHaveClass('text-green-600');

    // Average slippage: -17.0 bps (favorable)
    const avgSlippage = screen.getByText('-17.0');
    expect(avgSlippage).toHaveClass('text-green-600');
  });

  it('shows positive values in red for unfavorable slippage', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        fill_price: '150.25',
        fill_quantity: 100,
        slippage: '0.25', // Unfavorable - paid more
        slippage_bps: '17',
      }),
    ];

    render(<SlippageStats traces={traces} />);

    // Total slippage: $25.00 (unfavorable)
    const totalSlippage = screen.getByText('$25.00');
    expect(totalSlippage).toHaveClass('text-red-600');

    // Average and worst slippage: +17.0 bps (unfavorable)
    const bpsElements = screen.getAllByText('+17.0');
    expect(bpsElements).toHaveLength(2);
    bpsElements.forEach(el => expect(el).toHaveClass('text-red-600'));
  });

  it('handles all null slippage traces gracefully', () => {
    const traces: SignalTrace[] = [
      createTrace({
        trace_id: 'trace-1',
        fill_price: null,
        slippage: null,
        slippage_bps: null,
      }),
      createTrace({
        trace_id: 'trace-2',
        fill_price: null,
        slippage: null,
        slippage_bps: null,
      }),
    ];

    render(<SlippageStats traces={traces} />);

    // Should show zeros when no filled traces
    expect(screen.getByText('$0.00')).toBeInTheDocument();
    // Avg and worst both show +0.0
    const bpsElements = screen.getAllByText('+0.0');
    expect(bpsElements).toHaveLength(2);
    expect(screen.getByText('0%')).toBeInTheDocument();
  });
});
