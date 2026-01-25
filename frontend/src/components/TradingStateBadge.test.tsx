// frontend/src/components/TradingStateBadge.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TradingStateBadge } from './TradingStateBadge';

describe('TradingStateBadge', () => {
  it('shows green badge for RUNNING', () => {
    render(<TradingStateBadge state="RUNNING" />);
    const badge = screen.getByText('🟢 RUNNING');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-green-100');
  });

  it('shows yellow badge for PAUSED', () => {
    render(<TradingStateBadge state="PAUSED" />);
    const badge = screen.getByText('🟡 PAUSED');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-yellow-100');
  });

  it('shows red badge for HALTED', () => {
    render(<TradingStateBadge state="HALTED" />);
    const badge = screen.getByText('🔴 HALTED');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-red-100');
  });

  it('applies pulse animation for HALTED', () => {
    render(<TradingStateBadge state="HALTED" />);
    const badge = screen.getByText('🔴 HALTED');
    expect(badge).toHaveClass('animate-pulse');
  });
});
