// frontend/src/pages/BacktestPage.tsx
import { BacktestForm } from '../components/BacktestForm';
import { BacktestResults } from '../components/BacktestResults';
import { useBacktest } from '../hooks/useBacktest';

export function BacktestPage() {
  const { mutate, data, isPending, isError, error } = useBacktest();

  return (
    <>
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Backtest</h1>
        <p className="text-sm text-gray-500 mt-1">
          Test your strategy on historical data
        </p>
      </div>

      {/* Form */}
      <div className="mb-8">
        <BacktestForm onSubmit={mutate} isLoading={isPending} />
      </div>

      {/* Error State */}
      {isError && (
        <div className="mb-8 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-600">
            Error running backtest: {error?.message || 'Unknown error'}
          </p>
        </div>
      )}

      {/* Backtest Failed */}
      {data?.status === 'failed' && (
        <div className="mb-8 bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-600">
            Backtest failed: {data.error || 'Unknown error'}
          </p>
        </div>
      )}

      {/* Results */}
      {data?.status === 'completed' && data.result && (
        <BacktestResults result={data.result} />
      )}
    </>
  );
}
