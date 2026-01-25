// frontend/src/components/StorageDashboard.tsx
import type { StorageStats } from '../types';

interface StorageDashboardProps {
  stats: StorageStats | null;
  isLoading?: boolean;
  error?: string | null;
}

export function StorageDashboard({ stats, isLoading, error }: StorageDashboardProps) {
  if (isLoading) {
    return <div className="p-4">Loading storage statistics...</div>;
  }

  if (error) {
    return <div className="p-4 text-red-600">Error: {error}</div>;
  }

  if (!stats) {
    return <div className="p-4">No storage data available</div>;
  }

  return (
    <div className="p-4 space-y-6">
      {/* Database Overview */}
      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-2">Database Size</h2>
        <div className="text-3xl font-bold text-blue-600">{stats.database_size_pretty}</div>
        <div className="text-sm text-gray-500">
          Last updated: {new Date(stats.timestamp).toLocaleString()}
        </div>
      </div>

      {/* Tables */}
      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-4">Tables</h2>
        <table className="w-full">
          <thead>
            <tr className="text-left text-gray-600 border-b">
              <th className="pb-2">Table</th>
              <th className="pb-2">Rows</th>
              <th className="pb-2">Size</th>
              <th className="pb-2">Type</th>
            </tr>
          </thead>
          <tbody>
            {stats.tables.map((table) => (
              <tr key={table.table_name} className="border-b last:border-0">
                <td className="py-2 font-medium">{table.table_name}</td>
                <td className="py-2">{table.row_count.toLocaleString()}</td>
                <td className="py-2">{table.size_pretty}</td>
                <td className="py-2">
                  {table.is_hypertable && (
                    <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded">
                      Hypertable
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Compression Stats */}
      {Object.keys(stats.compression).length > 0 && (
        <div className="bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-semibold mb-4">Compression</h2>
          {Object.entries(stats.compression).map(([tableName, compression]) => (
            <div key={tableName} className="mb-4 last:mb-0">
              <h3 className="font-medium">{tableName}</h3>
              <div className="grid grid-cols-2 gap-4 mt-2">
                <div>
                  <div className="text-sm text-gray-500">Chunks Compressed</div>
                  <div>
                    {compression.compressed_chunks} / {compression.total_chunks} chunks compressed
                  </div>
                </div>
                {compression.compression_ratio && (
                  <div>
                    <div className="text-sm text-gray-500">Compression Ratio</div>
                    <div className="text-green-600 font-semibold">
                      {compression.compression_ratio.toFixed(1)}x
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
