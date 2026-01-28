// frontend/src/components/GreeksTrendChart.tsx
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

interface TrendPoint {
  timestamp: string;
  delta: number;
  gamma: number;
  vega: number;
  theta: number;
}

interface GreeksTrendChartProps {
  data: TrendPoint[];
  selectedMetrics?: ('delta' | 'gamma' | 'vega' | 'theta')[];
}

const metricColors = {
  delta: '#3B82F6', // blue
  gamma: '#10B981', // green
  vega: '#8B5CF6', // purple
  theta: '#F59E0B', // amber
};

export function GreeksTrendChart({
  data,
  selectedMetrics = ['delta', 'gamma'],
}: GreeksTrendChartProps) {
  if (data.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Greeks Trend</h3>
        <div className="h-64 flex items-center justify-center text-gray-500">
          No trend data available
        </div>
      </div>
    );
  }

  const formatTimestamp = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatValue = (value: number) => {
    if (Math.abs(value) >= 1000) {
      return `${(value / 1000).toFixed(1)}K`;
    }
    return value.toFixed(0);
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Greeks Trend</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
            <XAxis
              dataKey="timestamp"
              tickFormatter={formatTimestamp}
              tick={{ fontSize: 12 }}
              stroke="#9CA3AF"
            />
            <YAxis
              tickFormatter={formatValue}
              tick={{ fontSize: 12 }}
              stroke="#9CA3AF"
            />
            <Tooltip
              formatter={(value) => [`$${formatValue(value as number)}`, '']}
              labelFormatter={(label) => formatTimestamp(String(label))}
            />
            <Legend />
            {selectedMetrics.includes('delta') && (
              <Line
                type="monotone"
                dataKey="delta"
                stroke={metricColors.delta}
                strokeWidth={2}
                dot={false}
                name="Delta"
              />
            )}
            {selectedMetrics.includes('gamma') && (
              <Line
                type="monotone"
                dataKey="gamma"
                stroke={metricColors.gamma}
                strokeWidth={2}
                dot={false}
                name="Gamma"
              />
            )}
            {selectedMetrics.includes('vega') && (
              <Line
                type="monotone"
                dataKey="vega"
                stroke={metricColors.vega}
                strokeWidth={2}
                dot={false}
                name="Vega"
              />
            )}
            {selectedMetrics.includes('theta') && (
              <Line
                type="monotone"
                dataKey="theta"
                stroke={metricColors.theta}
                strokeWidth={2}
                dot={false}
                name="Theta"
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
