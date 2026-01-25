// frontend/src/components/ComponentHealthCard.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ComponentHealthCard } from './ComponentHealthCard';
import { ComponentHealth } from '../types';

describe('ComponentHealthCard', () => {
  const healthyComponent: ComponentHealth = {
    component: 'redis',
    status: 'healthy',
    latency_ms: 5.2,
    last_check: '2026-01-25T10:00:00Z',
    message: null,
  };

  it('renders component name', () => {
    render(<ComponentHealthCard component={healthyComponent} />);

    expect(screen.getByText('redis')).toBeInTheDocument();
  });

  it('renders status badge', () => {
    render(<ComponentHealthCard component={healthyComponent} />);

    expect(screen.getByText('healthy')).toBeInTheDocument();
  });

  it('renders latency when available', () => {
    render(<ComponentHealthCard component={healthyComponent} />);

    expect(screen.getByText(/5.2\s*ms/)).toBeInTheDocument();
  });

  it('renders message when present', () => {
    const componentWithMessage: ComponentHealth = {
      ...healthyComponent,
      status: 'down',
      message: 'Connection refused',
    };

    render(<ComponentHealthCard component={componentWithMessage} />);

    expect(screen.getByText('Connection refused')).toBeInTheDocument();
  });

  it('does not render latency when null', () => {
    const componentNoLatency: ComponentHealth = {
      ...healthyComponent,
      latency_ms: null,
    };

    render(<ComponentHealthCard component={componentNoLatency} />);

    expect(screen.queryByText(/ms/)).not.toBeInTheDocument();
  });

  it('renders last check time', () => {
    render(<ComponentHealthCard component={healthyComponent} />);

    // Should show relative time or formatted date
    expect(screen.getByText(/Last check:/)).toBeInTheDocument();
  });
});
