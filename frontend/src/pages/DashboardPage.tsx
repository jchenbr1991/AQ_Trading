import { Header } from '../components/Header';
import { AccountSummary } from '../components/AccountSummary';
import { PositionsTable } from '../components/PositionsTable';
import { AlertsPanel } from '../components/AlertsPanel';
import { ErrorBanner } from '../components/ErrorBanner';
import { useAccount } from '../hooks/useAccount';
import { usePositions } from '../hooks/usePositions';
import { useTradingState } from '../hooks/useTradingState';
import { useAlerts } from '../hooks/useAlerts';
import { useFreshness } from '../hooks/useFreshness';
import { closePosition } from '../api/orders';

const ACCOUNT_ID = 'ACC001'; // TODO: Make configurable

export function DashboardPage() {
  const account = useAccount(ACCOUNT_ID);
  const positions = usePositions(ACCOUNT_ID);
  const tradingState = useTradingState();
  const alerts = useAlerts();

  const positionsFreshness = useFreshness(
    positions.dataUpdatedAt,
    positions.isError,
    positions.failureCount ?? 0
  );

  const handleKillSwitch = async () => {
    await tradingState.triggerKillSwitch();
  };

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
      <Header
        tradingState={tradingState.data?.state ?? 'RUNNING'}
        onKillSwitch={handleKillSwitch}
      />

      <main className="max-w-7xl mx-auto px-4 py-6">
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
      </main>
    </>
  );
}
