// frontend/src/components/GreeksSummaryCard.test.tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { GreeksSummaryCard } from './GreeksSummaryCard';
import type { AggregatedGreeks } from '../types';

const mockGreeks: AggregatedGreeks = {
  scope: 'ACCOUNT',
  scope_id: 'acc123',
  strategy_id: null,
  dollar_delta: 45000,
  gamma_dollar: 8000,
  gamma_pnl_1pct: 0.4,
  vega_per_1pct: 15000,
  theta_per_day: -2500,
  coverage_pct: 95.5,
  is_coverage_sufficient: true,
  has_high_risk_missing_legs: false,
  valid_legs_count: 10,
  total_legs_count: 10,
  staleness_seconds: 5,
  as_of_ts: new Date().toISOString(),
};

describe('GreeksSummaryCard', () => {
  it('renders all Greeks values', () => {
    render(<GreeksSummaryCard greeks={mockGreeks} />);

    expect(screen.getByText('Delta')).toBeInTheDocument();
    expect(screen.getByText('Gamma')).toBeInTheDocument();
    expect(screen.getByText('Vega')).toBeInTheDocument();
    expect(screen.getByText('Theta')).toBeInTheDocument();
  });

  it('shows coverage percentage', () => {
    render(<GreeksSummaryCard greeks={mockGreeks} />);

    expect(screen.getByText('95.5% coverage')).toBeInTheDocument();
  });

  it('shows staleness warning when stale', () => {
    const staleGreeks = { ...mockGreeks, staleness_seconds: 60 };
    render(<GreeksSummaryCard greeks={staleGreeks} />);

    expect(screen.getByText('60s stale')).toBeInTheDocument();
  });

  it('does not show staleness warning when fresh', () => {
    render(<GreeksSummaryCard greeks={mockGreeks} />);

    expect(screen.queryByText(/stale/)).not.toBeInTheDocument();
  });

  it('shows Account Greeks title for account scope', () => {
    render(<GreeksSummaryCard greeks={mockGreeks} />);

    expect(screen.getByText('Account Greeks')).toBeInTheDocument();
  });

  it('shows strategy name for strategy scope', () => {
    const strategyGreeks = { ...mockGreeks, scope: 'STRATEGY' as const, strategy_id: 'wheel_aapl' };
    render(<GreeksSummaryCard greeks={strategyGreeks} />);

    expect(screen.getByText('wheel_aapl')).toBeInTheDocument();
  });

  it('displays formatted Greek values with units', () => {
    render(<GreeksSummaryCard greeks={mockGreeks} />);

    // Delta: 45000 -> $45.0K
    expect(screen.getByText('$45.0K')).toBeInTheDocument();
    // Gamma: 8000 -> $8.0K
    expect(screen.getByText('$8.0K')).toBeInTheDocument();
    // Vega: 15000 -> $15.0K/1%
    expect(screen.getByText('$15.0K/1%')).toBeInTheDocument();
    // Theta: -2500 -> $-2.5K/day
    expect(screen.getByText('$-2.5K/day')).toBeInTheDocument();
  });

  it('shows utilization percentages', () => {
    render(<GreeksSummaryCard greeks={mockGreeks} />);

    // Delta: 45000 / 50000 = 90%
    expect(screen.getByText('90% of limit')).toBeInTheDocument();
    // Gamma: 8000 / 10000 = 80%
    expect(screen.getByText('80% of limit')).toBeInTheDocument();
  });

  it('applies green styling for sufficient coverage', () => {
    render(<GreeksSummaryCard greeks={mockGreeks} />);

    const coverageBadge = screen.getByText('95.5% coverage');
    expect(coverageBadge).toHaveClass('bg-green-100', 'text-green-800');
  });

  it('applies yellow styling for insufficient coverage', () => {
    const insufficientCoverage = { ...mockGreeks, is_coverage_sufficient: false };
    render(<GreeksSummaryCard greeks={insufficientCoverage} />);

    const coverageBadge = screen.getByText('95.5% coverage');
    expect(coverageBadge).toHaveClass('bg-yellow-100', 'text-yellow-800');
  });

  it('applies red color to negative values', () => {
    render(<GreeksSummaryCard greeks={mockGreeks} />);

    // Theta is negative (-2500)
    const thetaValue = screen.getByText('$-2.5K/day');
    expect(thetaValue).toHaveClass('text-red-600');
  });
});
