// frontend/src/components/BacktestForm.tsx
import { useState } from 'react';
import type { BacktestRequest } from '../types';

interface BacktestFormProps {
  onSubmit: (request: BacktestRequest) => void;
  isLoading: boolean;
}

export function BacktestForm({ onSubmit, isLoading }: BacktestFormProps) {
  const [symbol, setSymbol] = useState('AAPL');
  const [initialCapital, setInitialCapital] = useState('100000');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2024-12-31');
  const [lookbackPeriod, setLookbackPeriod] = useState('20');
  const [threshold, setThreshold] = useState('2.0');
  const [positionSize, setPositionSize] = useState('100');
  const [slippageBps, setSlippageBps] = useState('5');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const request: BacktestRequest = {
      strategy_class: 'MeanReversionStrategy',
      strategy_params: {
        lookback_period: parseInt(lookbackPeriod, 10),
        threshold: parseFloat(threshold),
        position_size: parseInt(positionSize, 10),
      },
      symbol,
      start_date: startDate,
      end_date: endDate,
      initial_capital: initialCapital,
      slippage_bps: parseInt(slippageBps, 10),
    };

    onSubmit(request);
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-medium text-gray-900 mb-4">Backtest Configuration</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Symbol */}
        <div>
          <label htmlFor="symbol" className="block text-sm font-medium text-gray-700">
            Symbol
          </label>
          <input
            type="text"
            id="symbol"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
            required
          />
        </div>

        {/* Initial Capital */}
        <div>
          <label htmlFor="initial-capital" className="block text-sm font-medium text-gray-700">
            Initial Capital ($)
          </label>
          <input
            type="number"
            id="initial-capital"
            value={initialCapital}
            onChange={(e) => setInitialCapital(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
            min="1000"
            required
          />
        </div>

        {/* Start Date */}
        <div>
          <label htmlFor="start-date" className="block text-sm font-medium text-gray-700">
            Start Date
          </label>
          <input
            type="date"
            id="start-date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
            required
          />
        </div>

        {/* End Date */}
        <div>
          <label htmlFor="end-date" className="block text-sm font-medium text-gray-700">
            End Date
          </label>
          <input
            type="date"
            id="end-date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
            required
          />
        </div>

        {/* Lookback Period */}
        <div>
          <label htmlFor="lookback-period" className="block text-sm font-medium text-gray-700">
            Lookback Period (bars)
          </label>
          <input
            type="number"
            id="lookback-period"
            value={lookbackPeriod}
            onChange={(e) => setLookbackPeriod(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
            min="1"
            required
          />
        </div>

        {/* Threshold */}
        <div>
          <label htmlFor="threshold" className="block text-sm font-medium text-gray-700">
            Threshold (std devs)
          </label>
          <input
            type="number"
            id="threshold"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            step="0.1"
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
            min="0.1"
            required
          />
        </div>

        {/* Position Size */}
        <div>
          <label htmlFor="position-size" className="block text-sm font-medium text-gray-700">
            Position Size (shares)
          </label>
          <input
            type="number"
            id="position-size"
            value={positionSize}
            onChange={(e) => setPositionSize(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
            min="1"
            required
          />
        </div>

        {/* Slippage */}
        <div>
          <label htmlFor="slippage-bps" className="block text-sm font-medium text-gray-700">
            Slippage (basis points)
          </label>
          <input
            type="number"
            id="slippage-bps"
            value={slippageBps}
            onChange={(e) => setSlippageBps(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
            min="0"
            required
          />
        </div>
      </div>

      <div className="mt-6">
        <button
          type="submit"
          disabled={isLoading}
          className="w-full md:w-auto px-6 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-blue-300 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Running Backtest...' : 'Run Backtest'}
        </button>
      </div>
    </form>
  );
}
