// frontend/src/pages/AgentsPage.tsx
import { useState } from 'react';
import { useAgentResults, useInvokeAgent } from '../hooks/useAgents';
import type { AgentRole, AgentResultResponse } from '../types';

const AGENT_ROLES: { value: AgentRole; label: string; description: string }[] = [
  {
    value: 'researcher',
    label: 'Researcher',
    description: 'Gathers market data and research information',
  },
  {
    value: 'analyst',
    label: 'Analyst',
    description: 'Analyzes data and generates insights',
  },
  {
    value: 'risk_controller',
    label: 'Risk Controller',
    description: 'Monitors and manages risk exposure',
  },
  {
    value: 'ops',
    label: 'Operations',
    description: 'Handles operational tasks and maintenance',
  },
];

const PERMISSION_MATRIX: Record<AgentRole, string[]> = {
  researcher: ['read_market_data', 'fetch_news', 'query_database'],
  analyst: ['read_market_data', 'generate_reports', 'query_database', 'run_backtest'],
  risk_controller: ['read_positions', 'check_limits', 'send_alerts', 'modify_limits'],
  ops: ['read_system_status', 'restart_services', 'clear_caches', 'run_maintenance'],
};

function formatDuration(ms: number | null): string {
  if (ms === null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTimestamp(dateStr: string): string {
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function StatusBadge({ success }: { success: boolean }) {
  return (
    <span
      className={`px-2 py-1 text-xs font-medium rounded ${
        success
          ? 'bg-green-100 text-green-800'
          : 'bg-red-100 text-red-800'
      }`}
    >
      {success ? 'Success' : 'Failed'}
    </span>
  );
}

function RoleBadge({ role }: { role: AgentRole }) {
  const colorMap: Record<AgentRole, string> = {
    researcher: 'bg-blue-100 text-blue-800',
    analyst: 'bg-purple-100 text-purple-800',
    risk_controller: 'bg-yellow-100 text-yellow-800',
    ops: 'bg-gray-100 text-gray-800',
  };

  return (
    <span className={`px-2 py-1 text-xs font-medium rounded ${colorMap[role]}`}>
      {role.replace('_', ' ')}
    </span>
  );
}

function ResultDetailModal({
  result,
  onClose,
}: {
  result: AgentResultResponse | null;
  onClose: () => void;
}) {
  if (!result) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black bg-opacity-50" onClick={onClose} />
      <div className="relative bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 p-6 max-h-[80vh] overflow-y-auto">
        <h2 className="text-xl font-bold mb-4">Result Details</h2>
        <div className="space-y-3 text-sm">
          <div>
            <span className="font-medium">ID:</span>{' '}
            <span className="font-mono text-xs">{result.id}</span>
          </div>
          <div>
            <span className="font-medium">Role:</span> <RoleBadge role={result.role} />
          </div>
          <div>
            <span className="font-medium">Task:</span> {result.task}
          </div>
          <div>
            <span className="font-medium">Status:</span> <StatusBadge success={result.success} />
          </div>
          <div>
            <span className="font-medium">Started:</span> {formatTimestamp(result.started_at)}
          </div>
          <div>
            <span className="font-medium">Duration:</span> {formatDuration(result.duration_ms)}
          </div>
          {result.error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-red-800">
              <span className="font-medium">Error:</span> {result.error}
            </div>
          )}
          {result.result && (
            <div className="mt-4">
              <span className="font-medium">Result:</span>
              <pre className="mt-2 p-3 bg-gray-50 border border-gray-200 rounded text-xs overflow-x-auto">
                {JSON.stringify(result.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
        <div className="flex justify-end mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function PermissionMatrix() {
  return (
    <div className="bg-white rounded-lg shadow p-4 mb-6">
      <h2 className="text-lg font-medium mb-4">Permission Matrix</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-gray-500">Role</th>
              <th className="px-3 py-2 text-left font-medium text-gray-500">Permissions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {AGENT_ROLES.map((role) => (
              <tr key={role.value} className="hover:bg-gray-50">
                <td className="px-3 py-2">
                  <RoleBadge role={role.value} />
                  <div className="text-xs text-gray-500 mt-1">{role.description}</div>
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {PERMISSION_MATRIX[role.value].map((perm) => (
                      <span
                        key={perm}
                        className="px-2 py-0.5 text-xs bg-gray-100 text-gray-700 rounded"
                      >
                        {perm}
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AgentsPage() {
  const [selectedRole, setSelectedRole] = useState<AgentRole>('researcher');
  const [task, setTask] = useState('');
  const [context, setContext] = useState('{}');
  const [contextError, setContextError] = useState<string | null>(null);
  const [selectedResult, setSelectedResult] = useState<AgentResultResponse | null>(null);

  const { data, isLoading, isError, error } = useAgentResults();
  const invokeMutation = useInvokeAgent();

  const handleContextChange = (value: string) => {
    setContext(value);
    try {
      JSON.parse(value);
      setContextError(null);
    } catch {
      setContextError('Invalid JSON');
    }
  };

  const handleInvoke = async () => {
    if (!task.trim()) return;
    if (contextError) return;

    try {
      const parsedContext = context.trim() ? JSON.parse(context) : undefined;
      await invokeMutation.mutateAsync({
        role: selectedRole,
        task: task.trim(),
        context: parsedContext,
      });
      // Clear form on success
      setTask('');
      setContext('{}');
    } catch {
      // Error is handled by mutation state
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Agents</h1>

      {/* Invoke Form */}
      <div className="bg-white rounded-lg shadow p-4 mb-6">
        <h2 className="text-lg font-medium mb-4">Invoke Agent Task</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Agent Role
            </label>
            <select
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value as AgentRole)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {AGENT_ROLES.map((role) => (
                <option key={role.value} value={role.value}>
                  {role.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-500 mt-1">
              {AGENT_ROLES.find((r) => r.value === selectedRole)?.description}
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Task
            </label>
            <input
              type="text"
              value={task}
              onChange={(e) => setTask(e.target.value)}
              placeholder="Enter task description..."
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Context (JSON)
            </label>
            <textarea
              value={context}
              onChange={(e) => handleContextChange(e.target.value)}
              placeholder='{"key": "value"}'
              rows={3}
              className={`w-full px-3 py-2 border rounded-md font-mono text-sm focus:outline-none focus:ring-2 ${
                contextError
                  ? 'border-red-300 focus:ring-red-500'
                  : 'border-gray-300 focus:ring-blue-500'
              }`}
            />
            {contextError && (
              <p className="text-xs text-red-500 mt-1">{contextError}</p>
            )}
          </div>
          <div className="md:col-span-2">
            <button
              onClick={handleInvoke}
              disabled={!task.trim() || !!contextError || invokeMutation.isPending}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {invokeMutation.isPending ? 'Invoking...' : 'Invoke Agent'}
            </button>
          </div>
        </div>

        {invokeMutation.isError && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-red-700">
            {invokeMutation.error instanceof Error
              ? invokeMutation.error.message
              : 'Failed to invoke agent'}
          </div>
        )}

        {invokeMutation.isSuccess && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded text-green-700">
            Agent task invoked successfully. Check results below.
          </div>
        )}
      </div>

      {/* Permission Matrix */}
      <PermissionMatrix />

      {/* Results History */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200">
          <h2 className="text-lg font-medium">Results History</h2>
          {data && (
            <p className="text-sm text-gray-500">
              Showing {data.results.length} of {data.total} results
            </p>
          )}
        </div>

        {isError && (
          <div className="p-4 bg-red-50 text-red-700">
            {error instanceof Error ? error.message : 'Failed to load results'}
          </div>
        )}

        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">ID</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Role</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Task</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Status</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Started</th>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Duration</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {isLoading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                  Loading...
                </td>
              </tr>
            ) : !data?.results || data.results.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-16 text-center text-gray-500">
                  <div className="text-lg">No agent results yet</div>
                  <div className="text-sm mt-2">
                    Invoke an agent task above to see results here
                  </div>
                </td>
              </tr>
            ) : (
              data.results.map((result) => (
                <tr key={result.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">
                    {result.id.substring(0, 8)}...
                  </td>
                  <td className="px-4 py-3">
                    <RoleBadge role={result.role} />
                  </td>
                  <td className="px-4 py-3 text-gray-700 max-w-xs truncate">
                    {result.task}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge success={result.success} />
                  </td>
                  <td className="px-4 py-3 text-gray-600 text-sm">
                    {formatTimestamp(result.started_at)}
                  </td>
                  <td className="px-4 py-3 text-gray-600 text-sm">
                    {formatDuration(result.duration_ms)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => setSelectedResult(result)}
                      className="px-3 py-1 text-sm text-blue-600 hover:text-blue-800 hover:underline"
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Result Detail Modal */}
      {selectedResult && (
        <ResultDetailModal
          result={selectedResult}
          onClose={() => setSelectedResult(null)}
        />
      )}
    </div>
  );
}
