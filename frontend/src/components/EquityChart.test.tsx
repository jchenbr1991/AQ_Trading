// frontend/src/components/EquityChart.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EquityChart } from './EquityChart';
import type { EquityCurvePoint } from '../types';

// Mock recharts to avoid rendering issues in tests
vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <svg role="img" data-testid="line-chart">
      {children}
    </svg>
  ),
  Line: ({ dataKey, name }: { dataKey: string; name?: string }) => (
    <line data-testid={`line-${dataKey}`} data-name={name} />
  ),
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => <div data-testid="legend" />,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

describe('EquityChart', () => {
  const mockEquityCurve: EquityCurvePoint[] = [
    { timestamp: '2024-01-01T00:00:00Z', equity: 100000 },
    { timestamp: '2024-01-02T00:00:00Z', equity: 101000 },
    { timestamp: '2024-01-03T00:00:00Z', equity: 102500 },
  ];

  const mockBenchmarkData: EquityCurvePoint[] = [
    { timestamp: '2024-01-01T00:00:00Z', equity: 100000 },
    { timestamp: '2024-01-02T00:00:00Z', equity: 100500 },
    { timestamp: '2024-01-03T00:00:00Z', equity: 101000 },
  ];

  it('renders equity curve chart', () => {
    render(<EquityChart data={mockEquityCurve} />);

    expect(screen.getByText('Equity Curve')).toBeInTheDocument();
    expect(screen.getByRole('img')).toBeInTheDocument();
  });

  it('renders without benchmark when benchmarkData is not provided', () => {
    render(<EquityChart data={mockEquityCurve} />);

    expect(screen.getByRole('img')).toBeInTheDocument();
    expect(screen.getByTestId('line-equity')).toBeInTheDocument();
    expect(screen.queryByTestId('line-benchmark')).not.toBeInTheDocument();
    expect(screen.queryByTestId('legend')).not.toBeInTheDocument();
  });

  it('renders benchmark line when benchmarkData is provided', () => {
    render(
      <EquityChart
        data={mockEquityCurve}
        benchmarkData={mockBenchmarkData}
        benchmarkSymbol="SPY"
      />
    );

    expect(screen.getByRole('img')).toBeInTheDocument();
    expect(screen.getByTestId('line-equity')).toBeInTheDocument();
    expect(screen.getByTestId('line-benchmark')).toBeInTheDocument();
    expect(screen.getByTestId('legend')).toBeInTheDocument();
  });

  it('renders with benchmarkData but no benchmarkSymbol', () => {
    render(<EquityChart data={mockEquityCurve} benchmarkData={mockBenchmarkData} />);

    expect(screen.getByTestId('line-benchmark')).toBeInTheDocument();
    expect(screen.getByTestId('legend')).toBeInTheDocument();
  });

  it('shows empty state when no data provided', () => {
    render(<EquityChart data={[]} />);

    expect(screen.getByText('No equity curve data available')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('does not render benchmark line when benchmarkData is empty array', () => {
    render(<EquityChart data={mockEquityCurve} benchmarkData={[]} />);

    expect(screen.getByTestId('line-equity')).toBeInTheDocument();
    expect(screen.queryByTestId('line-benchmark')).not.toBeInTheDocument();
    expect(screen.queryByTestId('legend')).not.toBeInTheDocument();
  });
});
