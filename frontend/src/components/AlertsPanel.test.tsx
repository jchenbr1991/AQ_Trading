// frontend/src/components/AlertsPanel.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AlertsPanel } from './AlertsPanel';
import type { ReconciliationAlert } from '../types';

describe('AlertsPanel', () => {
  it('renders loading state', () => {
    render(<AlertsPanel alerts={undefined} isLoading={true} />);

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('renders empty state when alerts is undefined', () => {
    render(<AlertsPanel alerts={undefined} isLoading={false} />);

    expect(screen.getByText('No recent alerts')).toBeInTheDocument();
  });

  it('renders empty state when alerts is empty array', () => {
    render(<AlertsPanel alerts={[]} isLoading={false} />);

    expect(screen.getByText('No recent alerts')).toBeInTheDocument();
  });

  it('renders alerts list', () => {
    const mockAlerts: ReconciliationAlert[] = [
      {
        timestamp: '2024-01-15T10:30:00Z',
        severity: 'critical',
        type: 'POSITION_MISMATCH',
        symbol: 'AAPL',
        local_value: '100',
        message: 'Position mismatch detected',
      },
      {
        timestamp: '2024-01-15T10:25:00Z',
        severity: 'warning',
        type: 'PRICE_STALE',
        symbol: 'TSLA',
        local_value: null,
        message: 'Price data is stale',
      },
    ];

    render(<AlertsPanel alerts={mockAlerts} isLoading={false} />);

    expect(screen.getByText('POSITION_MISMATCH')).toBeInTheDocument();
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByText('Position mismatch detected')).toBeInTheDocument();
    expect(screen.getByText('PRICE_STALE')).toBeInTheDocument();
    expect(screen.getByText('TSLA')).toBeInTheDocument();
  });

  it('renders correct severity icons', () => {
    const mockAlerts: ReconciliationAlert[] = [
      {
        timestamp: '2024-01-15T10:30:00Z',
        severity: 'critical',
        type: 'ERROR',
        symbol: null,
        local_value: null,
        message: 'Critical error',
      },
      {
        timestamp: '2024-01-15T10:25:00Z',
        severity: 'warning',
        type: 'WARN',
        symbol: null,
        local_value: null,
        message: 'Warning message',
      },
      {
        timestamp: '2024-01-15T10:20:00Z',
        severity: 'info',
        type: 'INFO',
        symbol: null,
        local_value: null,
        message: 'Info message',
      },
    ];

    render(<AlertsPanel alerts={mockAlerts} isLoading={false} />);

    // Check severity icons are rendered
    expect(screen.getByText('Critical error')).toBeInTheDocument();
    expect(screen.getByText('Warning message')).toBeInTheDocument();
    expect(screen.getByText('Info message')).toBeInTheDocument();
  });

  it('renders header correctly', () => {
    render(<AlertsPanel alerts={[]} isLoading={false} />);

    expect(screen.getByText(/Reconciliation Alerts/)).toBeInTheDocument();
  });

  it('handles alert without symbol', () => {
    const mockAlerts: ReconciliationAlert[] = [
      {
        timestamp: '2024-01-15T10:30:00Z',
        severity: 'info',
        type: 'SYSTEM',
        symbol: null,
        local_value: null,
        message: 'System notification',
      },
    ];

    render(<AlertsPanel alerts={mockAlerts} isLoading={false} />);

    expect(screen.getByText('SYSTEM')).toBeInTheDocument();
    expect(screen.getByText('System notification')).toBeInTheDocument();
  });
});
