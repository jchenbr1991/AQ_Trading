// frontend/src/components/EquityChart.tsx
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { EquityCurvePoint } from '../types';

interface EquityChartProps {
  data: EquityCurvePoint[];
  benchmarkData?: EquityCurvePoint[];
  benchmarkSymbol?: string;
}

export function EquityChart({ data, benchmarkData, benchmarkSymbol }: EquityChartProps) {
  if (data.length === 0) {
    return (
      <div className="bg-gray-50 rounded-lg p-8 text-center text-gray-500">
        No equity curve data available
      </div>
    );
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  // Combine strategy and benchmark data by timestamp
  const chartData = data.map((point) => {
    const benchmarkPoint = benchmarkData?.find((b) => b.timestamp === point.timestamp);
    return {
      timestamp: point.timestamp,
      equity: point.equity,
      benchmark: benchmarkPoint ? benchmarkPoint.equity : null,
    };
  });

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <h3 className="text-lg font-medium text-gray-900 mb-4">Equity Curve</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="timestamp"
              tickFormatter={formatDate}
              tick={{ fontSize: 12 }}
              stroke="#6b7280"
            />
            <YAxis
              tickFormatter={formatCurrency}
              tick={{ fontSize: 12 }}
              stroke="#6b7280"
              width={80}
            />
            <Tooltip
              formatter={(value: number, name: string) => [
                formatCurrency(value),
                name === 'benchmark' ? benchmarkSymbol || 'Benchmark' : 'Strategy',
              ]}
              labelFormatter={(label) => new Date(String(label)).toLocaleDateString()}
              contentStyle={{ fontSize: 12 }}
            />
            {benchmarkData && benchmarkData.length > 0 && (
              <Legend
                verticalAlign="top"
                height={36}
                formatter={(value: string) =>
                  value === 'benchmark' ? benchmarkSymbol || 'Benchmark' : 'Strategy'
                }
              />
            )}
            <Line
              type="monotone"
              dataKey="equity"
              stroke="#2563eb"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              name="equity"
            />
            {benchmarkData && benchmarkData.length > 0 && (
              <Line
                type="monotone"
                dataKey="benchmark"
                stroke="#9ca3af"
                strokeDasharray="5 5"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                name="benchmark"
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
