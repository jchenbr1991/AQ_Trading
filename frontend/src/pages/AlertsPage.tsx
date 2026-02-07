// frontend/src/pages/AlertsPage.tsx
import { AlertStats } from '../components/AlertStats';
import { AlertsTable } from '../components/AlertsTable';

export function AlertsPage() {
  return (
    <>
      <h1 className="text-2xl font-bold mb-6">Alerts</h1>
      <AlertStats />
      <AlertsTable />
    </>
  );
}
