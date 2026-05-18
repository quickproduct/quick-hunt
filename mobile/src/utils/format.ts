import { Job, JobStatus, SendLogStatus } from '../types';

export function percent(num: number, denom: number): string {
  if (!denom) return '-';
  return `${Math.round((num / denom) * 100)}%`;
}

export function compactNumber(value?: number | null): string {
  if (value === undefined || value === null) return '0';
  return new Intl.NumberFormat('en-IN', { notation: value >= 10000 ? 'compact' : 'standard' }).format(value);
}

export function formatDate(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function formatRelative(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  const delta = Date.now() - date.getTime();
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (delta < minute) return 'just now';
  if (delta < hour) return `${Math.max(1, Math.floor(delta / minute))}m ago`;
  if (delta < day) return `${Math.floor(delta / hour)}h ago`;
  if (delta < 30 * day) return `${Math.floor(delta / day)}d ago`;
  return formatDate(value);
}

export function formatScore(job: Job): string {
  if (job.relevance_score === undefined || job.relevance_score === null) return '-';
  const raw = job.relevance_score > 1 ? job.relevance_score : job.relevance_score * 100;
  return `${Math.round(raw)} score`;
}

export function formatSalary(job: Job): string | null {
  if (!job.salary_min && !job.salary_max) return null;
  const currency = job.salary_currency || 'INR';
  const min = job.salary_min ? compactNumber(job.salary_min) : '';
  const max = job.salary_max ? compactNumber(job.salary_max) : '';
  return [currency, [min, max].filter(Boolean).join(' - ')].filter(Boolean).join(' ');
}

export function humanize(value?: string | null): string {
  if (!value) return '-';
  return value.replace(/_/g, ' ');
}

export function jobStatusTone(status?: JobStatus | string): 'mint' | 'cyan' | 'amber' | 'coral' | 'neutral' {
  switch (status) {
    case 'sent':
    case 'applied':
    case 'cover_generated':
      return 'mint';
    case 'scoring':
    case 'sending':
      return 'cyan';
    case 'pending_approval':
      return 'amber';
    case 'bounced':
    case 'error':
      return 'coral';
    default:
      return 'neutral';
  }
}

export function logStatusTone(status?: SendLogStatus | string): 'mint' | 'cyan' | 'amber' | 'coral' | 'neutral' {
  switch (status) {
    case 'delivered':
    case 'opened':
    case 'clicked':
      return 'mint';
    case 'sent':
    case 'queued':
    case 'dry_run':
      return 'cyan';
    case 'deferred':
    case 'soft_bounced':
    case 'blocked':
      return 'amber';
    case 'bounced':
    case 'failed':
      return 'coral';
    default:
      return 'neutral';
  }
}

export function todayISO(): string {
  return new Date().toISOString().split('T')[0] ?? '';
}

export function daysAgoISO(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString().split('T')[0] ?? '';
}
