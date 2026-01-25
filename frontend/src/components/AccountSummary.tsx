import type { AccountSummary as AccountSummaryType } from '../types';

interface AccountSummaryProps {
  account: AccountSummaryType | undefined;
  isLoading: boolean;
}

export function AccountSummary({ account, isLoading }: AccountSummaryProps) {
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(value);
  };

  const formatPnL = (value: number) => {
    const formatted = formatCurrency(Math.abs(value));
    return value >= 0 ? `+${formatted}` : `-${formatted}`;
  };

  if (isLoading || !account) {
    return (
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-lg shadow p-4 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-20 mb-2"></div>
            <div className="h-8 bg-gray-200 rounded w-32"></div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">Total Equity</p>
        <p className="text-2xl font-bold">{formatCurrency(account.total_equity)}</p>
      </div>
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">Cash</p>
        <p className="text-2xl font-bold">{formatCurrency(account.cash)}</p>
      </div>
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">Day P&L</p>
        <p className={`text-2xl font-bold ${account.day_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
          {formatPnL(account.day_pnl)}
        </p>
      </div>
    </div>
  );
}
