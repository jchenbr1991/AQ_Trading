// frontend/src/pages/AuditPage.tsx
import { useState } from 'react';
import { AuditStats } from '../components/AuditStats';
import { AuditFilters, type AuditFilterValues } from '../components/AuditFilters';
import { AuditTable } from '../components/AuditTable';

export function AuditPage() {
  const [filters, setFilters] = useState<AuditFilterValues>({});

  return (
    <>
      <h1 className="text-2xl font-bold mb-6">Audit Logs</h1>
      <AuditStats />
      <AuditFilters filters={filters} onFiltersChange={setFilters} />
      <AuditTable filters={filters} />
    </>
  );
}
