// frontend/src/hooks/useFreshness.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useFreshness } from './useFreshness';

describe('useFreshness', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns live when data is fresh (< 10s)', () => {
    const now = Date.now();
    const { result } = renderHook(() =>
      useFreshness(now - 5000, false, 0) // 5 seconds ago
    );

    expect(result.current.state).toBe('live');
    expect(result.current.ageSeconds).toBeLessThan(10);
  });

  it('returns stale when data is 10-30s old', () => {
    const now = Date.now();
    const { result } = renderHook(() =>
      useFreshness(now - 15000, false, 0) // 15 seconds ago
    );

    expect(result.current.state).toBe('stale');
  });

  it('returns error when data is > 30s old', () => {
    const now = Date.now();
    const { result } = renderHook(() =>
      useFreshness(now - 35000, false, 0) // 35 seconds ago
    );

    expect(result.current.state).toBe('error');
  });

  it('returns error when fetch failed 3+ times', () => {
    const now = Date.now();
    const { result } = renderHook(() =>
      useFreshness(now - 5000, true, 3) // Fresh data but 3 failures
    );

    expect(result.current.state).toBe('error');
    expect(result.current.failureCount).toBe(3);
  });

  it('updates age over time', () => {
    const now = Date.now();
    const { result } = renderHook(() =>
      useFreshness(now - 5000, false, 0)
    );

    expect(result.current.state).toBe('live');

    // Advance time by 10 seconds
    act(() => {
      vi.advanceTimersByTime(10000);
    });

    // Now should be stale (15s old)
    expect(result.current.ageSeconds).toBeGreaterThanOrEqual(10);
  });
});
