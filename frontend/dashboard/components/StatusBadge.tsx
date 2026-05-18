'use client';

const STATUS_COLORS: Record<string, string> = {
  // ── Job statuses ────────────────────────────────────────────────────────
  new:              'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  scoring:          'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400',
  filtered:         'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  pending_approval: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  cover_generated:  'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  sending:          'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400',
  sent:             'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
  applied:          'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  bounced:          'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  ignored:          'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500',
  error:            'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  // ── Send log statuses ───────────────────────────────────────────────────
  queued:           'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
  sent_log:         'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
  delivered:        'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  opened:           'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  clicked:          'bg-violet-200 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300',
  // Temporary failures — amber tones
  soft_bounced:     'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  deferred:         'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  // Permanent failures — red
  blocked:          'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  failed:           'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400',
  // Permanent failures — red
  spam:             'bg-red-200 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  unsubscribed:     'bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
  dry_run:          'bg-orange-100 text-orange-600 dark:bg-orange-900/20 dark:text-orange-400',
  // ── Portals ─────────────────────────────────────────────────────────────
  naukri:    'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  indeed:    'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
  glassdoor: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  linkedin:  'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  angellist: 'bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-400',
};

// Human-readable labels for statuses
export const STATUS_LABELS: Record<string, string> = {
  new:              'New',
  scoring:          'Scoring',
  filtered:         'Filtered',
  pending_approval: 'Pending Approval',
  cover_generated:  'Cover Ready',
  sending:          'Sending',
  sent:             'Sent',
  applied:          'Applied',
  bounced:          'Bounced',
  queued:           'Queued',
  delivered:        'Delivered',
  opened:           'Opened',
  clicked:          'Clicked',
  soft_bounced:     'Soft Bounce (retry 48h)',
  blocked:          'Blocked (permanent)',
  deferred:         'Deferred (Brevo retrying ~36h)',
  failed:           'Failed',
  spam:             'Spam',
  unsubscribed:     'Unsubscribed',
  dry_run:          'Dry Run',
};

interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

export default function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const color = STATUS_COLORS[status] || 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300';
  const padding = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm';
  const label = STATUS_LABELS[status] ?? status.replace(/_/g, ' ');
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${padding} ${color}`}>
      {label}
    </span>
  );
}
