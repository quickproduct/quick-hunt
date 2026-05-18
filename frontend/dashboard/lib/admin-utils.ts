export function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return '\u2014';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 3_600_000) return `${(ms / 60_000).toFixed(1)}m`;
  const hours = Math.floor(ms / 3_600_000);
  const mins = Math.floor((ms % 3_600_000) / 60_000);
  return `${hours}h ${mins}m`;
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return '\u2014';
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 0) return 'just now';
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function fmtAbsolute(iso: string | null | undefined): string {
  if (!iso) return '';
  return new Date(iso).toLocaleString();
}

export function getTaskCategory(taskName: string): string {
  if (taskName.includes('scrape') || taskName.includes('backfill') || taskName.includes('placeholder'))
    return 'scraping';
  if (taskName.includes('cover') || taskName.includes('fill_missing') || taskName.includes('score'))
    return 'ai';
  if (taskName.includes('email') || taskName.includes('send') || taskName.includes('retry'))
    return 'email';
  return 'maintenance';
}

export function getCategoryColor(category: string): string {
  switch (category) {
    case 'scraping': return 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300';
    case 'ai': return 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300';
    case 'email': return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
    default: return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
  }
}

export function getQueueHealth(messages: number, consumers: number): 'healthy' | 'warning' | 'critical' {
  if (consumers === 0 && messages > 0) return 'critical';
  if (messages > 1000) return 'critical';
  if (messages > 100 || (consumers === 0 && messages > 0)) return 'warning';
  return 'healthy';
}
