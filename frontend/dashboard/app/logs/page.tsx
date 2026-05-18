'use client';

import { Fragment, useEffect, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { ChevronDown, ChevronRight, RefreshCw, ExternalLink } from 'lucide-react';
import StatusBadge, { STATUS_LABELS } from '../../components/StatusBadge';
import { getSendLogs, type SendLog } from '../../lib/api';

const STATUS_OPTIONS = [
  '',
  // Positive
  'sent', 'delivered', 'opened', 'clicked',
  // Brevo retrying (temporary)
  'soft_bounced', 'deferred',
  // Permanent failures
  'bounced', 'blocked', 'spam', 'unsubscribed',
  // Housekeeping
  'queued', 'dry_run',
];

export default function LogsPage() {
  const [logs, setLogs] = useState<SendLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchLogs = async (showLoader = false) => {
    if (showLoader) setLoading(true);
    try {
      const params: Record<string, unknown> = { limit: 100 };
      if (statusFilter) params.status = statusFilter;
      const data = await getSendLogs(params);
      setLogs(data);
      setLastRefresh(new Date());
    } catch {
      // keep existing data on auto-refresh errors
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs(true);
  }, [statusFilter]);

  useEffect(() => {
    const interval = setInterval(() => fetchLogs(false), 30000);
    return () => clearInterval(interval);
  }, [statusFilter]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Send Logs</h1>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            Last updated {formatDistanceToNow(lastRefresh, { addSuffix: true })} · auto-refreshes every 30s
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Status filter */}
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="text-sm border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {STATUS_OPTIONS.map(s => (
              <option key={s} value={s}>{s === '' ? 'All statuses' : STATUS_LABELS[s] ?? s.replace(/_/g, ' ')}</option>
            ))}
          </select>

          <button
            onClick={() => fetchLogs(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-48">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            {statusFilter ? `No logs with status "${statusFilter}"` : 'No send logs yet'}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
                <th className="px-4 py-3 w-8"></th>
                <th className="px-4 py-3 font-medium">Job / Company</th>
                <th className="px-4 py-3 font-medium">To Email</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Provider</th>
                <th className="px-4 py-3 font-medium">Sent</th>
                <th className="px-4 py-3 font-medium">Delivered</th>
                <th className="px-4 py-3 font-medium">Opened</th>
                <th className="px-4 py-3 font-medium">Retries</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
              {logs.map(log => (
                <Fragment key={log.id}>
                  <tr
                    className="hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer"
                    onClick={() => setExpanded(expanded === log.id ? null : log.id)}
                  >
                    <td className="px-4 py-3 text-gray-400">
                      {expanded === log.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </td>
                    <td className="px-4 py-3 max-w-[180px]">
                      {log.job_title ? (
                        <>
                          <p className="text-gray-800 dark:text-gray-200 font-medium truncate">{log.job_title}</p>
                          <p className="text-xs text-gray-400 truncate">{log.company || '—'}</p>
                        </>
                      ) : (
                        <p className="text-gray-500 dark:text-gray-400 truncate">{log.subject || '—'}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400 max-w-[160px] truncate">{log.to_email}</td>
                    <td className="px-4 py-3"><StatusBadge status={log.status} /></td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400 capitalize">{log.provider || '—'}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {log.sent_at ? formatDistanceToNow(new Date(log.sent_at), { addSuffix: true }) : '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {log.delivered_at ? formatDistanceToNow(new Date(log.delivered_at), { addSuffix: true }) : '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {log.opened_at ? formatDistanceToNow(new Date(log.opened_at), { addSuffix: true }) : '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-500">{log.retry_count}</td>
                  </tr>
                  {expanded === log.id && (
                    <tr>
                      <td colSpan={9} className="px-4 py-3 bg-gray-50 dark:bg-gray-800/30">
                        <div className="space-y-2 text-xs text-gray-600 dark:text-gray-400">
                          {log.subject && <p><strong>Subject:</strong> {log.subject}</p>}
                          {log.body_snippet && <p><strong>Preview:</strong> {log.body_snippet}</p>}
                          {log.provider_message_id && <p><strong>Message ID:</strong> {log.provider_message_id}</p>}
                          {log.clicked_at && (
                            <p><strong>Clicked:</strong> {formatDistanceToNow(new Date(log.clicked_at), { addSuffix: true })}</p>
                          )}
                          {log.error_message && (
                            <p className="text-red-500"><strong>Error:</strong> {log.error_message}</p>
                          )}
                          {log.job_id && (
                            <a
                              href={`/jobs/${log.job_id}`}
                              className="inline-flex items-center gap-1 text-blue-600 hover:underline"
                              onClick={e => e.stopPropagation()}
                            >
                              View job <ExternalLink size={11} />
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p className="text-xs text-gray-400 text-right">
        Showing {logs.length} log{logs.length !== 1 ? 's' : ''}
        {statusFilter ? ` with status "${statusFilter}"` : ''}
      </p>
    </div>
  );
}
