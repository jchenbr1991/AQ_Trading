// frontend/src/pages/GreeksPage.tsx
import { useState } from 'react';
import { useAccountId } from '../contexts/AccountContext';
import { useGreeksOverview, useAcknowledgeAlert } from '../hooks/useGreeks';
import { GreeksSummaryCard } from '../components/GreeksSummaryCard';
import { GreeksAlertsPanel } from '../components/GreeksAlertsPanel';
import { GreeksStrategyBreakdown } from '../components/GreeksStrategyBreakdown';
import { GreeksTrendChart } from '../components/GreeksTrendChart';

export function GreeksPage() {
  const accountId = useAccountId();
  const { data, isLoading, isError, error } = useGreeksOverview(accountId);
  const acknowledgeMutation = useAcknowledgeAlert();
  const [selectedTab, setSelectedTab] = useState<'account' | 'strategies'>('account');

  // Mock trend data - in production, fetch from API
  const [trendData] = useState([
    { timestamp: new Date(Date.now() - 3600000).toISOString(), delta: 45000, gamma: 8000, vega: 15000, theta: -2500 },
    { timestamp: new Date(Date.now() - 2700000).toISOString(), delta: 47000, gamma: 8500, vega: 15500, theta: -2600 },
    { timestamp: new Date(Date.now() - 1800000).toISOString(), delta: 48000, gamma: 9000, vega: 16000, theta: -2700 },
    { timestamp: new Date(Date.now() - 900000).toISOString(), delta: 46000, gamma: 8200, vega: 15200, theta: -2550 },
    { timestamp: new Date().toISOString(), delta: 50000, gamma: 8800, vega: 15800, theta: -2800 },
  ]);

  const handleAcknowledge = (alertId: string) => {
    acknowledgeMutation.mutate({ alertId, acknowledgedBy: 'user' });
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-100 p-8">
        <div className="max-w-7xl mx-auto">
          <p className="text-gray-500">Loading Greeks data...</p>
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="min-h-screen bg-gray-100 p-8">
        <div className="max-w-7xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-600">Error loading Greeks: {error?.message}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Greeks Monitoring</h1>
          <p className="text-sm text-gray-500 mt-1">
            Account: {accountId} | Last updated: {new Date(data.account.as_of_ts).toLocaleString()}
          </p>
        </div>

        {/* Tabs */}
        <div className="mb-6">
          <div className="border-b border-gray-200">
            <nav className="-mb-px flex space-x-8">
              <button
                onClick={() => setSelectedTab('account')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  selectedTab === 'account'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                Account Summary
              </button>
              <button
                onClick={() => setSelectedTab('strategies')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  selectedTab === 'strategies'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                By Strategy
              </button>
            </nav>
          </div>
        </div>

        {/* Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main content */}
          <div className="lg:col-span-2 space-y-6">
            {selectedTab === 'account' ? (
              <>
                <GreeksSummaryCard greeks={data.account} />
                <GreeksTrendChart data={trendData} selectedMetrics={['delta', 'gamma']} />
              </>
            ) : (
              <GreeksStrategyBreakdown strategies={data.strategies} />
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            <GreeksAlertsPanel
              alerts={data.alerts}
              onAcknowledge={handleAcknowledge}
            />

            {/* Quick stats */}
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Quick Stats</h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-500">Total Positions</span>
                  <span className="font-medium">{data.account.total_legs_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Valid Greeks</span>
                  <span className="font-medium">{data.account.valid_legs_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Strategies</span>
                  <span className="font-medium">{Object.keys(data.strategies).length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Active Alerts</span>
                  <span className={`font-medium ${data.alerts.length > 0 ? 'text-red-600' : ''}`}>
                    {data.alerts.length}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
