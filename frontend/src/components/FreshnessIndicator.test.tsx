// frontend/src/components/FreshnessIndicator.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FreshnessIndicator } from './FreshnessIndicator';

describe('FreshnessIndicator', () => {
  it('shows green indicator for live state', () => {
    render(<FreshnessIndicator state="live" ageSeconds={5} />);
    expect(screen.getByText('🟢')).toBeInTheDocument();
    expect(screen.getByText(/5s ago/)).toBeInTheDocument();
  });

  it('shows yellow indicator for stale state', () => {
    render(<FreshnessIndicator state="stale" ageSeconds={15} />);
    expect(screen.getByText('🟡')).toBeInTheDocument();
  });

  it('shows red indicator for error state', () => {
    render(<FreshnessIndicator state="error" ageSeconds={45} />);
    expect(screen.getByText('🔴')).toBeInTheDocument();
  });

  it('formats time correctly for minutes', () => {
    render(<FreshnessIndicator state="error" ageSeconds={120} />);
    expect(screen.getByText(/2m ago/)).toBeInTheDocument();
  });
});
