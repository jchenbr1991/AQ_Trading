// frontend/src/components/HealthStatusBadge.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HealthStatusBadge } from './HealthStatusBadge';

describe('HealthStatusBadge', () => {
  it('renders healthy status with green color', () => {
    render(<HealthStatusBadge status="healthy" />);

    const badge = screen.getByText('healthy');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-green-100', 'text-green-800');
  });

  it('renders degraded status with yellow color', () => {
    render(<HealthStatusBadge status="degraded" />);

    const badge = screen.getByText('degraded');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-yellow-100', 'text-yellow-800');
  });

  it('renders down status with red color', () => {
    render(<HealthStatusBadge status="down" />);

    const badge = screen.getByText('down');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-red-100', 'text-red-800');
  });

  it('renders unknown status with gray color', () => {
    render(<HealthStatusBadge status="unknown" />);

    const badge = screen.getByText('unknown');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-gray-100', 'text-gray-800');
  });

  it('accepts custom className', () => {
    render(<HealthStatusBadge status="healthy" className="ml-2" />);

    const badge = screen.getByText('healthy');
    expect(badge).toHaveClass('ml-2');
  });
});
