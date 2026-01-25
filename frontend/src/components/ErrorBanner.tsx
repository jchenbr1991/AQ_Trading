// frontend/src/components/ErrorBanner.tsx
interface ErrorBannerProps {
  failureCount: number;
  lastSuccessful?: string;
  onRetry: () => void;
}

export function ErrorBanner({ failureCount, lastSuccessful, onRetry }: ErrorBannerProps) {
  if (failureCount < 3) {
    return null;
  }

  const formatLastSuccessful = () => {
    if (!lastSuccessful) return 'Unknown';
    const date = new Date(lastSuccessful);
    const diff = Math.floor((Date.now() - date.getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    return `${Math.floor(diff / 60)}m ago`;
  };

  return (
    <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center">
          <span className="text-red-500 font-medium">
            🔴 Connection Error ({failureCount} failures)
          </span>
        </div>
        <button
          onClick={onRetry}
          className="px-3 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200"
        >
          Retry Now
        </button>
      </div>
      <p className="text-sm text-red-600 mt-1">
        Last successful update: {formatLastSuccessful()}
      </p>
    </div>
  );
}
