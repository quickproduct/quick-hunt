'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  Briefcase, Mail, FileText, Users, MousePointerClick, CheckCircle,
  AlertCircle, RefreshCw, Send, ChevronRight, XCircle, Clock,
  TrendingUp, AlertTriangle, Activity,
} from 'lucide-react';
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis,
  Tooltip, ResponsiveContainer,
} from 'recharts';
import { formatDistanceToNow } from 'date-fns';
import StatsCard from '../../components/StatsCard';
import StatusBadge from '../../components/StatusBadge';
import {
  getStats, getSendLogs, getSearchTasks, getCandidates,
  type Stats, type SendLog, type SearchTask, type Candidate,
} from '../../lib/api';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

const SEARCH_STATUS_COLORS: Record<string, string> = {
  running: 'text-blue-600 bg-blue-50 dark:bg-blue-900/30',
  completed: 'text-green-600 bg-green-50 dark:bg-green-900/30',
  error: 'text-red-600 bg-red-50 dark:bg-red-900/30',
  queued: 'text-yellow-600 bg-yellow-50 dark:bg-yellow-900/30',
};

function pct(num: number, denom: number): string {
  if (!denom) return '—';
  return `${Math.round((num / denom) * 100)}%`;
}

function RateBar({ value, total, color = 'bg-blue-500' }: { value: number; total: number; color?: string }) {
  const width = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="w-full bg-gray-100 dark:bg-gray-800 rounded-full h-1.5 mt-1">
      <div className={`${color} h-1.5 rounded-full transition-all`} style={{ width: `${width}%` }} />
    </div>
  );
}

function FunnelStep({
  label, value, prev, color, icon: Icon,
}: {
  label: string; value: number; prev?: number; color: string; icon: React.ElementType;
}) {
  const convRate = prev !== undefined ? pct(value, prev) : null;
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className={`shrink-0 p-1.5 rounded-lg ${color}`}>
        <Icon size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-700 dark:text-gray-300">{label}</span>
          <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 tabular-nums">{value.toLocaleString()}</span>
        </div>
        {convRate && (
          <div className="flex items-center gap-1 mt-0.5">
            <ChevronRight size={10} className="text-gray-400" />
            <span className="text-xs text-gray-400">{convRate} of previous</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [logs, setLogs] = useState<SendLog[]>([]);
  const [searches, setSearches] = useState<SearchTask[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [candidateId, setCandidateId] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchData = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    setError(null);
    try {
      const params = candidateId ? { candidate_id: candidateId } : undefined;
      const [s, l, t] = await Promise.all([
        getStats(params),
        getSendLogs({ limit: 5 }),
        getSearchTasks(5),
      ]);
      setStats(s);
      setLogs(l);
      setSearches(t);
      setLastRefresh(new Date());
    } catch {
      setError('Failed to load dashboard data. Check that the API is running.');
    } finally {
      setLoading(false);
    }
  }, [candidateId]);

  // Load candidates once on mount for the filter dropdown
  useEffect(() => {
    getCandidates().then(setCandidates).catch(() => {});
  }, []);

  useEffect(() => {
    fetchData(true);

    let interval: ReturnType<typeof setInterval> | null = null;
    const startInterval = () => {
      if (interval) return;
      interval = setInterval(() => fetchData(false), 30000);
    };
    const stopInterval = () => {
      if (interval) { clearInterval(interval); interval = null; }
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') { fetchData(false); startInterval(); }
      else stopInterval();
    };

    startInterval();
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => { stopInterval(); document.removeEventListener('visibilitychange', onVisibilityChange); };
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <AlertCircle className="text-red-500" size={32} />
        <p className="text-red-600 dark:text-red-400">{error}</p>
        <button
          onClick={() => fetchData(true)}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          Retry
        </button>
      </div>
    );
  }

  const portalData = Object.entries(stats?.jobs_by_portal || {}).map(([name, value]) => ({ name, value }));
  const statusData = Object.entries(stats?.jobs_by_status || {}).map(([name, value]) => ({
    name: name.replace(/_/g, ' '),
    value,
  }));

  const totalJobs = stats?.total_jobs || 0;
  const sent = stats?.emails_sent || 0;
  const unsentHr = Math.max(0, (stats?.jobs_with_hr_email || 0) - sent);
  const unsentCover = Math.max(0, (stats?.cover_letters_generated || 0) - sent);
  const ready = stats?.jobs_ready || 0;
  const delivered = stats?.emails_delivered || 0;
  const opened = stats?.emails_opened || 0;
  const clicked = stats?.emails_clicked || 0;
  const bounced = stats?.emails_bounced || 0;
  const softBounced = stats?.emails_soft_bounced || 0;
  const missingHr = stats?.jobs_missing_hr || 0;
  const pendingApproval = stats?.jobs_pending_approval || 0;

  // Delivery rate denominator: all emails that have a terminal outcome (delivered or bounced)
  const attemptedDelivery = delivered + bounced + softBounced;
  const deliveryRate = pct(delivered, attemptedDelivery || sent);
  const openRate = pct(opened, delivered || sent);
  const clickRate = pct(clicked, opened || delivered || sent);
  const bounceRate = pct(bounced + softBounced, sent);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Dashboard</h1>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            Last updated {formatDistanceToNow(lastRefresh, { addSuffix: true })} · auto-refreshes every 30s
          </p>
        </div>
        <div className="flex items-center gap-2">
          {candidates.length > 0 && (
            <select
              value={candidateId}
              onChange={(e) => setCandidateId(e.target.value)}
              className="text-sm border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All Candidates</option>
              {candidates.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          )}
          <button
            onClick={() => fetchData(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </div>

      {/* Top stats row — 5 columns via inline style to avoid Tailwind JIT purge */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: '1rem' }}>
        <StatsCard title="Total Jobs" value={totalJobs} icon={Briefcase} color="blue" />
        <StatsCard title="HR Emails Found" value={unsentHr} icon={Users} color="orange" />
        <StatsCard title="Cover Letters" value={unsentCover} icon={FileText} color="purple" />
        <StatsCard title="Ready to Send" value={ready} icon={Send} color="green" />
        <StatsCard title="Emails Sent" value={sent} icon={Mail} color="blue" />
      </div>

      {/* Application Pipeline funnel + Email Performance side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pipeline funnel */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <div className="flex items-center gap-2 mb-1">
            <Activity size={16} className="text-blue-500" />
            <h2 className="font-semibold text-gray-900 dark:text-gray-100">Application Pipeline</h2>
          </div>
          <p className="text-xs text-gray-400 mb-4">Conversion at each stage</p>
          <div className="divide-y divide-gray-100 dark:divide-gray-800">
            <FunnelStep label="Jobs Scraped" value={totalJobs} color="bg-blue-50 dark:bg-blue-900/30 text-blue-600" icon={Briefcase} />
            <FunnelStep label="HR Email Found (unsent)" value={unsentHr} prev={totalJobs} color="bg-orange-50 dark:bg-orange-900/30 text-orange-600" icon={Users} />
            <FunnelStep label="Cover Letter Generated (unsent)" value={unsentCover} prev={unsentHr} color="bg-purple-50 dark:bg-purple-900/30 text-purple-600" icon={FileText} />
            <FunnelStep label="Ready to Send" value={ready} prev={unsentCover} color="bg-green-50 dark:bg-green-900/30 text-green-600" icon={Send} />
            <FunnelStep label="Emails Sent" value={sent} prev={ready} color="bg-blue-50 dark:bg-blue-900/30 text-blue-600" icon={Mail} />
            <FunnelStep label="Delivered" value={delivered} prev={sent} color="bg-teal-50 dark:bg-teal-900/30 text-teal-600" icon={CheckCircle} />
            <FunnelStep label="Opened" value={opened} prev={delivered} color="bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600" icon={Mail} />
            <FunnelStep label="Clicked" value={clicked} prev={opened} color="bg-violet-50 dark:bg-violet-900/30 text-violet-600" icon={MousePointerClick} />
          </div>
        </div>

        {/* Email performance + bottlenecks */}
        <div className="flex flex-col gap-4">
          {/* Email performance */}
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
            <div className="flex items-center gap-2 mb-1">
              <TrendingUp size={16} className="text-green-500" />
              <h2 className="font-semibold text-gray-900 dark:text-gray-100">Email Performance</h2>
            </div>
            <p className="text-xs text-gray-400 mb-4">Rates across {sent.toLocaleString()} emails sent</p>
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Delivery Rate</span>
                  <span className="font-semibold text-gray-800 dark:text-gray-200">{deliveryRate} <span className="text-gray-400 font-normal">({delivered} / {sent})</span></span>
                </div>
                <RateBar value={delivered} total={sent} color="bg-teal-500" />
              </div>
              <div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Open Rate</span>
                  <span className="font-semibold text-gray-800 dark:text-gray-200">{openRate} <span className="text-gray-400 font-normal">({opened} / {delivered || sent})</span></span>
                </div>
                <RateBar value={opened} total={delivered || sent} color="bg-indigo-500" />
              </div>
              <div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Click Rate</span>
                  <span className="font-semibold text-gray-800 dark:text-gray-200">{clickRate} <span className="text-gray-400 font-normal">({clicked} / {opened || delivered || sent})</span></span>
                </div>
                <RateBar value={clicked} total={opened || delivered || sent} color="bg-violet-500" />
              </div>
              <div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Bounce Rate</span>
                  <span className="font-semibold text-gray-800 dark:text-gray-200">{bounceRate} <span className="text-gray-400 font-normal">({bounced + softBounced} / {sent})</span></span>
                </div>
                <RateBar value={bounced + softBounced} total={sent} color="bg-red-400" />
              </div>
            </div>
          </div>

          {/* Bottlenecks */}
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle size={16} className="text-yellow-500" />
              <h2 className="font-semibold text-gray-900 dark:text-gray-100">Bottlenecks</h2>
            </div>
            <p className="text-xs text-gray-400 mb-4">Items blocking the pipeline</p>
            <div className="space-y-2">
              <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-800">
                <div className="flex items-center gap-2">
                  <XCircle size={14} className="text-red-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">Missing HR Email</span>
                </div>
                <span className={`text-sm font-semibold tabular-nums ${missingHr > 50 ? 'text-red-600' : missingHr > 20 ? 'text-yellow-600' : 'text-gray-700 dark:text-gray-300'}`}>
                  {missingHr.toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-800">
                <div className="flex items-center gap-2">
                  <Clock size={14} className="text-yellow-500" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">Pending Approval</span>
                </div>
                <span className={`text-sm font-semibold tabular-nums ${pendingApproval > 20 ? 'text-yellow-600' : 'text-gray-700 dark:text-gray-300'}`}>
                  {pendingApproval.toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between py-2">
                <div className="flex items-center gap-2">
                  <AlertCircle size={14} className="text-orange-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">Soft Bounced (retryable)</span>
                </div>
                <span className={`text-sm font-semibold tabular-nums ${softBounced > 10 ? 'text-orange-600' : 'text-gray-700 dark:text-gray-300'}`}>
                  {softBounced.toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">Jobs by Portal</h2>
          {portalData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={portalData}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[200px] flex items-center justify-center text-gray-400">No data yet</div>
          )}
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">Jobs by Status</h2>
          {statusData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={statusData} cx="50%" cy="50%" outerRadius={75} dataKey="value" label={({ name }) => name}>
                  {statusData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[200px] flex items-center justify-center text-gray-400">No data yet</div>
          )}
        </div>
      </div>

      {/* Recent searches + recent applications */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">Recent Searches</h2>
          {searches.length === 0 ? (
            <p className="text-gray-400 dark:text-gray-500 text-sm">No searches yet</p>
          ) : (
            <div className="space-y-3">
              {searches.map(task => (
                <div key={task.id} className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {task.job_titles?.join(', ') || '—'}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {task.portals?.join(', ')} · {task.jobs_found} jobs found
                    </p>
                  </div>
                  <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${SEARCH_STATUS_COLORS[task.status] || 'text-gray-500 bg-gray-100'}`}>
                    {task.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">Recent Applications</h2>
          {logs.length === 0 ? (
            <p className="text-gray-400 dark:text-gray-500 text-sm">No applications sent yet</p>
          ) : (
            <div className="space-y-3">
              {logs.map(log => (
                <div key={log.id} className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {log.job_title || log.subject || log.to_email}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {log.company ? `${log.company} · ` : ''}{log.to_email}
                    </p>
                  </div>
                  <div className="shrink-0 flex flex-col items-end gap-1">
                    <StatusBadge status={log.status} />
                    <span className="text-xs text-gray-400">
                      {log.sent_at ? formatDistanceToNow(new Date(log.sent_at), { addSuffix: true }) : '—'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
