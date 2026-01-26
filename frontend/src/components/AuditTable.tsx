// frontend/src/components/AuditTable.tsx
import { useState } from 'react';
import { useAuditLogs } from '../hooks';
import type { AuditLog, AuditSeverity } from '../types';
import type { AuditFilterValues } from './AuditFilters';

interface AuditTableProps {
  filters: AuditFilterValues;
}

function SeverityBadge({ severity }: { severity: AuditSeverity }) {
  const badgeClasses: Record<AuditSeverity, string> = {
    info: 'bg-blue-100 text-blue-800',
    warning: 'bg-yellow-100 text-yellow-800',
    critical: 'bg-red-100 text-red-800',
  };

  const labels: Record<AuditSeverity, string> = {
    info: 'INFO',
    warning: 'WARNING',
    critical: 'CRITICAL',
  };

  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full ${badgeClasses[severity]}`}>
      {labels[severity]}
    </span>
  );
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function JsonViewer({ data, label }: { data: Record<string, unknown> | null; label: string }) {
  if (!data) {
    return (
      <div className="text-sm text-gray-500">
        <span className="font-medium">{label}:</span> None
      </div>
    );
  }

  return (
    <div className="text-sm">
      <span className="font-medium text-gray-700">{label}:</span>
      <pre className="mt-1 bg-gray-50 p-2 rounded text-xs overflow-x-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

function ExpandedRow({ log }: { log: AuditLog }) {
  return (
    <tr>
      <td colSpan={6} className="px-4 py-3 bg-gray-50">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-3">
            <div className="text-sm">
              <span className="font-medium text-gray-700">Event ID:</span>{' '}
              <span className="font-mono text-gray-600">{log.event_id}</span>
            </div>
            <div className="text-sm">
              <span className="font-medium text-gray-700">Request ID:</span>{' '}
              <span className="font-mono text-gray-600">{log.request_id}</span>
            </div>
            <div className="text-sm">
              <span className="font-medium text-gray-700">Correlation ID:</span>{' '}
              <span className="font-mono text-gray-600">{log.correlation_id || 'None'}</span>
            </div>
            <div className="text-sm">
              <span className="font-medium text-gray-700">Source:</span>{' '}
              <span className="text-gray-600">{log.source}</span>
            </div>
            <div className="text-sm">
              <span className="font-medium text-gray-700">Service:</span>{' '}
              <span className="text-gray-600">{log.service} (v{log.version})</span>
            </div>
            <div className="text-sm">
              <span className="font-medium text-gray-700">Value Mode:</span>{' '}
              <span className="text-gray-600">{log.value_mode}</span>
            </div>
          </div>
          <div className="space-y-3">
            <JsonViewer data={log.old_value} label="Old Value" />
            <JsonViewer data={log.new_value} label="New Value" />
            {log.metadata && Object.keys(log.metadata).length > 0 && (
              <JsonViewer data={log.metadata} label="Metadata" />
            )}
          </div>
        </div>
      </td>
    </tr>
  );
}

const PAGE_SIZE = 20;

export function AuditTable({ filters }: AuditTableProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(0);

  const params = {
    ...filters,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  };

  const { data, isLoading, error } = useAuditLogs(params);

  const toggleExpanded = (eventId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(eventId)) {
        next.delete(eventId);
      } else {
        next.add(eventId);
      }
      return next;
    });
  };

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-4 py-3 border-b flex items-center justify-between">
        <h2 className="text-lg font-semibold">Audit Logs</h2>
        {data && (
          <span className="text-sm text-gray-500">
            {data.total} total logs
          </span>
        )}
      </div>

      {error && (
        <div className="p-4 bg-red-50 text-red-700">
          Failed to load audit logs: {error.message}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500 w-8"></th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Timestamp</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Event Type</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Actor</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Resource</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Severity</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                  Loading...
                </td>
              </tr>
            ) : !data?.logs || data.logs.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                  No audit logs found
                </td>
              </tr>
            ) : (
              data.logs.flatMap((log: AuditLog) => {
                const isExpanded = expandedIds.has(log.event_id);
                const rows = [
                  <tr
                    key={log.event_id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => toggleExpanded(log.event_id)}
                  >
                    <td className="px-4 py-3 text-gray-400">
                      {isExpanded ? (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {formatTime(log.timestamp)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900 font-mono">
                      {log.event_type}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      <div>{log.actor_id}</div>
                      <div className="text-xs text-gray-400">{log.actor_type}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      <div>{log.resource_type}/{log.resource_id}</div>
                    </td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity={log.severity} />
                    </td>
                  </tr>,
                ];
                if (isExpanded) {
                  rows.push(<ExpandedRow key={`${log.event_id}-expanded`} log={log} />);
                }
                return rows;
              })
            )}
          </tbody>
        </table>
      </div>

      {data && totalPages > 1 && (
        <div className="px-4 py-3 border-t flex items-center justify-between">
          <div className="text-sm text-gray-500">
            Showing {page * PAGE_SIZE + 1} to {Math.min((page + 1) * PAGE_SIZE, data.total)} of {data.total}
          </div>
          <div className="flex space-x-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="px-3 py-1 text-sm text-gray-600">
              Page {page + 1} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
