'use client';

import { ChevronDown, ChevronUp, AlertCircle, RefreshCw } from 'lucide-react';
import { useState, type ReactNode } from 'react';

export function SectionCard({
  title,
  icon,
  badge,
  defaultOpen = true,
  loading = false,
  error,
  onRetry,
  actions,
  className,
  children,
}: {
  title: string;
  icon?: ReactNode;
  badge?: ReactNode;
  defaultOpen?: boolean;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={`bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 ${className || ''}`}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 w-full p-5 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors rounded-t-xl"
      >
        {icon}
        <h2 className="font-semibold text-gray-900 dark:text-gray-100">{title}</h2>
        {badge}
        <div className="ml-auto flex items-center gap-2">
          {actions}
          {open ? (
            <ChevronUp size={16} className="text-gray-400" />
          ) : (
            <ChevronDown size={16} className="text-gray-400" />
          )}
        </div>
      </button>
      {open && (
        <div className="px-5 pb-5">
          {error && (
            <div className="flex items-center gap-2 mb-3 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
              <AlertCircle size={14} />
              <span className="flex-1">{error}</span>
              {onRetry && (
                <button onClick={onRetry} className="flex items-center gap-1 text-xs hover:underline">
                  <RefreshCw size={12} />
                  Retry
                </button>
              )}
            </div>
          )}
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" />
            </div>
          ) : (
            children
          )}
        </div>
      )}
    </div>
  );
}
