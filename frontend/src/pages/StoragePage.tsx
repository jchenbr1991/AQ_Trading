// frontend/src/pages/StoragePage.tsx
import { useStorage } from '../hooks/useStorage';
import { StorageDashboard } from '../components/StorageDashboard';

export function StoragePage() {
  const { data, isLoading, error } = useStorage();

  return (
    <div className="container mx-auto">
      <h1 className="text-2xl font-bold p-4">Storage Monitoring</h1>
      <StorageDashboard
        stats={data ?? null}
        isLoading={isLoading}
        error={error?.message}
      />
    </div>
  );
}
