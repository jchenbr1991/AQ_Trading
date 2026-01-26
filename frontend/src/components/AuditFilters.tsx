// frontend/src/components/AuditFilters.tsx
import { useState, useEffect } from 'react';
import type { AuditEventType, ResourceType } from '../types';

export interface AuditFilterValues {
  event_type?: string;
  resource_type?: string;
  actor_id?: string;
  start_time?: string;
  end_time?: string;
}

interface AuditFiltersProps {
  filters: AuditFilterValues;
  onFiltersChange: (filters: AuditFilterValues) => void;
}

const EVENT_TYPES: AuditEventType[] = [
  'order_placed',
  'order_acknowledged',
  'order_filled',
  'order_cancelled',
  'order_rejected',
  'config_created',
  'config_updated',
  'config_deleted',
  'alert_emitted',
  'alert_acknowledged',
  'alert_resolved',
  'system_started',
  'system_stopped',
  'health_changed',
  'auth_login',
  'auth_logout',
  'auth_failed',
  'permission_changed',
];

const RESOURCE_TYPES: ResourceType[] = [
  'order',
  'position',
  'config',
  'alert',
  'strategy',
  'account',
  'permission',
  'session',
];

export function AuditFilters({ filters, onFiltersChange }: AuditFiltersProps) {
  const [localFilters, setLocalFilters] = useState<AuditFilterValues>(filters);

  useEffect(() => {
    setLocalFilters(filters);
  }, [filters]);

  const handleChange = (key: keyof AuditFilterValues, value: string) => {
    const newFilters = {
      ...localFilters,
      [key]: value || undefined,
    };
    setLocalFilters(newFilters);
  };

  const handleApply = () => {
    onFiltersChange(localFilters);
  };

  const handleReset = () => {
    const emptyFilters: AuditFilterValues = {};
    setLocalFilters(emptyFilters);
    onFiltersChange(emptyFilters);
  };

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Filters</h2>
        <div className="flex space-x-2">
          <button
            onClick={handleReset}
            className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
          >
            Reset
          </button>
          <button
            onClick={handleApply}
            className="px-3 py-1 text-sm bg-gray-800 text-white rounded hover:bg-gray-700"
          >
            Apply
          </button>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Event Type
          </label>
          <select
            value={localFilters.event_type || ''}
            onChange={(e) => handleChange('event_type', e.target.value)}
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
          >
            <option value="">All</option>
            {EVENT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Resource Type
          </label>
          <select
            value={localFilters.resource_type || ''}
            onChange={(e) => handleChange('resource_type', e.target.value)}
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
          >
            <option value="">All</option>
            {RESOURCE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Actor ID
          </label>
          <input
            type="text"
            value={localFilters.actor_id || ''}
            onChange={(e) => handleChange('actor_id', e.target.value)}
            placeholder="Enter actor ID"
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Start Time
          </label>
          <input
            type="datetime-local"
            value={localFilters.start_time || ''}
            onChange={(e) => handleChange('start_time', e.target.value)}
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            End Time
          </label>
          <input
            type="datetime-local"
            value={localFilters.end_time || ''}
            onChange={(e) => handleChange('end_time', e.target.value)}
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-400"
          />
        </div>
      </div>
    </div>
  );
}
