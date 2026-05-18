'use client';

import { CheckCircle, XCircle, AlertCircle, Clock, Loader2 } from 'lucide-react';

const STATUS_STYLES: Record<string, { bg: string; icon: React.ElementType }> = {
  running: { bg: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300', icon: Loader2 },
  success: { bg: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300', icon: CheckCircle },
  failure: { bg: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300', icon: XCircle },
  timeout: { bg: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300', icon: AlertCircle },
  skipped: { bg: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300', icon: Clock },
};

export function AdminStatusBadge({ status, size = 'sm' }: { status: string; size?: 'sm' | 'md' }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.skipped;
  const Icon = style.icon;
  const iconSize = size === 'sm' ? 12 : 14;
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm';
  const px = size === 'sm' ? 'px-2 py-0.5' : 'px-3 py-1';

  return (
    <span className={`inline-flex items-center gap-1 ${px} rounded-full ${textSize} font-medium ${style.bg}`}>
      <Icon size={iconSize} className={status === 'running' ? 'animate-spin' : ''} />
      {status}
    </span>
  );
}

export function CircuitBadge({ state }: { state: string }) {
  const styles: Record<string, string> = {
    closed: 'bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400',
    open: 'bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400',
    half_open: 'bg-yellow-50 dark:bg-yellow-900/30 text-yellow-600 dark:text-yellow-400',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${styles[state] || styles.closed}`}>
      {state}
    </span>
  );
}
