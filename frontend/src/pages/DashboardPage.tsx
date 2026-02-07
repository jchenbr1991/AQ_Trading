import { AccountSummary } from '../components/AccountSummary';
import { PositionsTable } from '../components/PositionsTable';
import { AlertsPanel } from '../components/AlertsPanel';
import { ErrorBanner } from '../components/ErrorBanner';
import { useAccountId } from '../contexts/AccountContext';
import { useAccount } from '../hooks/useAccount';
import { usePositions } from '../hooks/usePositions';
import { useTradingState } from '../hooks/useTradingState';
import { useFreshness } from '../hooks/useFreshness';
import { useQuery } from '@tanstack/react-query';
import { fetchRecentAlerts } from '../api/reconciliation';
import { closePosition } from '../api/orders';

export function DashboardPage() {
  const accountId = useAccountId();
  const account = useAccount(accountId);
  const positions = usePositions(accountId);
  const tradingState = useTradingState();
  const alerts = useQuery({
    queryKey: ['reconciliation', 'recent'],
    queryFn: fetchRecentAlerts,
    refetchInterval: 30000,
  });

  const positionsFreshness = useFreshness(
    positions.dataUpdatedAt,
    positions.isError,
    positions.failureCount ?? 0
  );

  const handleClosePosition = async (symbol: string) => {
    await closePosition({
      symbol,
      quantity: 'all',
      order_type: 'market',
      time_in_force: 'IOC',
    });
    positions.refetch();
  };

  return (
    <>
      <ErrorBanner
        failureCount={positions.failureCount ?? 0}
        lastSuccessful={positions.dataUpdatedAt ? new Date(positions.dataUpdatedAt).toISOString() : undefined}
        onRetry={() => positions.refetch()}
      />

      <AccountSummary
        account={account.data}
        isLoading={account.isLoading}
      />

      <PositionsTable
        positions={positions.data}
        isLoading={positions.isLoading}
        tradingState={tradingState.data?.state ?? 'RUNNING'}
        freshness={positionsFreshness}
        onClosePosition={handleClosePosition}
      />

      <AlertsPanel
        alerts={alerts.data}
        isLoading={alerts.isLoading}
      />
    </>
  );
}
