// frontend/src/components/StorageDashboard.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StorageDashboard } from './StorageDashboard';
import type { StorageStats } from '../types';

describe('StorageDashboard', () => {
  const mockStats: StorageStats = {
    database_size_bytes: 1048576,
    database_size_pretty: '1 MB',
    timestamp: '2026-01-25T12:00:00Z',
    tables: [
      {
        table_name: 'transactions',
        row_count: 10000,
        size_bytes: 524288,
        size_pretty: '512 KB',
        is_hypertable: true,
      },
      {
        table_name: 'positions',
        row_count: 50,
        size_bytes: 8192,
        size_pretty: '8 KB',
        is_hypertable: false,
      },
    ],
    compression: {
      transactions: {
        total_chunks: 10,
        compressed_chunks: 7,
        compression_ratio: 4.0,
      },
    },
  };

  it('renders database size', () => {
    render(<StorageDashboard stats={mockStats} />);
    expect(screen.getByText('1 MB')).toBeInTheDocument();
  });

  it('renders table list', () => {
    render(<StorageDashboard stats={mockStats} />);
    // transactions appears in both table list and compression section
    expect(screen.getAllByText('transactions').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('positions')).toBeInTheDocument();
  });

  it('shows hypertable badge for hypertables', () => {
    render(<StorageDashboard stats={mockStats} />);
    expect(screen.getByText('Hypertable')).toBeInTheDocument();
  });

  it('shows compression stats when available', () => {
    render(<StorageDashboard stats={mockStats} />);
    expect(screen.getByText(/7.*\/.*10.*chunks compressed/i)).toBeInTheDocument();
  });

  it('renders loading state', () => {
    render(<StorageDashboard stats={null} isLoading={true} />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('renders error state', () => {
    render(<StorageDashboard stats={null} error="Failed to load" />);
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
  });

  it('renders empty state when no stats', () => {
    render(<StorageDashboard stats={null} />);
    expect(screen.getByText(/no storage data/i)).toBeInTheDocument();
  });
});
