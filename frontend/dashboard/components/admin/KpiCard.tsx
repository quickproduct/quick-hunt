'use client';

import { type ReactNode } from 'react';

export function KpiCard({
  label,
  value,
  icon,
  trend,
}: {
  label: string;
  value: string | number | null;
  icon: ReactNode;
  trend?: 'up' | 'down' | 'neutral';
}) {
  const trendColor = trend === 'up'
    ? 'text-green-500'
    : trend === 'down'
      ? 'text-red-500'
      : '';

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 flex items-center gap-3">
      <div className="p-2 bg-gray-50 dark:bg-gray-700 rounded-lg">{icon}</div>
      <div>
        <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
        <p className={`text-xl font-bold text-gray-900 dark:text-white ${trendColor}`}>
          {value ?? '\u2014'}
        </p>
      </div>
    </div>
  );
}
