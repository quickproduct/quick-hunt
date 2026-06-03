'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  AtSign,
  RefreshCw,
  CheckCircle,
  XCircle,
  Minus,
  Loader2,
  AlertTriangle,
  BarChart2,
  Mail,
  ShieldOff,
  Upload,
  FileText,
  TrendingDown,
  Send,
  Eye,
  X,
  Database,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import toast from 'react-hot-toast';
import StatsCard from '../../components/StatsCard';
import {
  getHrEmails,
  getHrEmailStats,
  getHrEmailDomainAnalysis,
  triggerHrEmailBackfill,
  validateHrEmailMx,
  updateHrEmail,
  importBrevoCSV,
  type HrEmail,
  type HrEmailStats,
  type DomainAnalysisRow,
  type BrevoImportResult,
} from '../../lib/api';

// ── Constants ─────────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  valid: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  bounced: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  fake: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300',
  invalid: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
  unknown: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const CHART_COLORS: Record<string, string> = {
  Valid: '#10b981',
  Bounced: '#ef4444',
  Fake: '#f59e0b',
  Invalid: '#dc2626',
  Unknown: '#6b7280',
};

const PAGE_SIZES = [20, 50, 100];

// ── Small helpers ─────────────────────────────────────────────────────────────

function MxIcon({ mx }: { mx?: boolean | null }) {
  if (mx === true) return <CheckCircle size={14} className="text-green-500" />;
  if (mx === false) return <XCircle size={14} className="text-red-500" />;
  return <Minus size={14} className="text-gray-400" />;
}

function Badge({ status }: { status: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium capitalize ${STATUS_COLORS[status] ?? STATUS_COLORS.unknown}`}>
      {status}
    </span>
  );
}

function fmt(n: number) {
  return n.toLocaleString();
}

function pct(num: number, denom: number): string {
  if (!denom) return '—';
  return (num / denom * 100).toFixed(1) + '%';
}

// ── Import Result Modal ───────────────────────────────────────────────────────

function ImportResultCard({
  result,
  onClose,
  onRefresh,
}: {
  result: BrevoImportResult;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const stats = [
    { label: 'Total CSV rows', value: fmt(result.total_rows), icon: FileText, color: 'text-blue-500' },
    { label: 'Unique messages', value: fmt(result.unique_messages), icon: Mail, color: 'text-blue-400' },
    { label: 'Unique HR emails', value: fmt(result.unique_emails), icon: AtSign, color: 'text-purple-500' },
    { label: 'Send logs updated', value: fmt(result.send_logs_updated), icon: CheckCircle, color: 'text-green-500' },
    { label: 'Jobs status updated', value: fmt(result.jobs_updated), icon: TrendingDown, color: 'text-orange-500' },
    { label: 'HR emails upserted', value: fmt(result.hr_emails_upserted), icon: Database, color: 'text-indigo-500' },
    { label: 'Unmatched messages', value: fmt(result.unmatched_messages), icon: AlertTriangle, color: 'text-yellow-500' },
  ];

  return (
    <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <CheckCircle size={18} className="text-green-600 dark:text-green-400" />
          <span className="font-semibold text-green-800 dark:text-green-300 text-sm">
            Import complete
          </span>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
          <X size={16} />
        </button>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        {stats.map(({ label, value, icon: Icon, color }) => (
          <div
            key={label}
            className="bg-white dark:bg-gray-800 rounded-lg px-3 py-2 border border-green-100 dark:border-green-800"
          >
            <div className="flex items-center gap-1.5 mb-0.5">
              <Icon size={12} className={color} />
              <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
            </div>
            <span className="text-base font-bold text-gray-800 dark:text-gray-100">{value}</span>
          </div>
        ))}
      </div>
      <button
        onClick={() => { onRefresh(); onClose(); }}
        className="text-sm text-green-700 dark:text-green-400 hover:underline"
      >
        Refresh page data →
      </button>
    </div>
  );
}

// ── CSV Drop Zone ─────────────────────────────────────────────────────────────

function CsvDropZone({ onImport }: { onImport: (file: File) => void }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.name.endsWith('.csv')) onImport(f);
    else toast.error('Please drop a .csv file');
  };

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onClick={() => inputRef.current?.click()}
      className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
        dragging
          ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/20'
          : 'border-gray-300 dark:border-gray-600 hover:border-blue-400 hover:bg-gray-50 dark:hover:bg-gray-750'
      }`}
    >
      <Upload size={28} className="mx-auto mb-2 text-gray-400" />
      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
        Drop your Brevo CSV export here
      </p>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
        or click to browse — expected columns: st_text, ts, sub, frm, email, tag, mid, link
      </p>
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onImport(f);
          e.target.value = '';
        }}
      />
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function HrEmailsPage() {
  const [emails, setEmails] = useState<HrEmail[]>([]);
  const [stats, setStats] = useState<HrEmailStats | null>(null);
  const [domainData, setDomainData] = useState<DomainAnalysisRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [backfillLoading, setBackfillLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<BrevoImportResult | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [validatingIds, setValidatingIds] = useState<Set<string>>(new Set());
  const [markingInvalidIds, setMarkingInvalidIds] = useState<Set<string>>(new Set());

  // Filters
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterHasBounces, setFilterHasBounces] = useState('');
  const [filterPlaceholder, setFilterPlaceholder] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Data fetching ───────────────────────────────────────────────────────────

  const fetchEmails = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const params: Record<string, unknown> = { page, page_size: pageSize };
        if (search) params.search = search;
        if (filterStatus) params.validation_status = filterStatus;
        if (filterHasBounces === 'yes') params.has_bounces = true;
        if (filterHasBounces === 'no') params.has_bounces = false;
        if (filterPlaceholder === 'yes') params.is_placeholder = true;
        if (filterPlaceholder === 'no') params.is_placeholder = false;
        const data = await getHrEmails(params);
        if (!signal?.aborted) setEmails(data);
      } catch (e: unknown) {
        if ((e as { name?: string }).name !== 'AbortError' && !signal?.aborted) {
          toast.error('Failed to load HR emails');
        }
      }
    },
    [search, filterStatus, filterHasBounces, filterPlaceholder, page, pageSize]
  );

  const fetchStats = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const [statsData, domainRows] = await Promise.all([
        getHrEmailStats(),
        getHrEmailDomainAnalysis({ limit: 30, sort_by: 'bounce_count', sort_dir: 'desc' }),
      ]);
      if (!signal?.aborted) {
        setStats(statsData);
        setDomainData(domainRows);
      }
    } catch {
      if (!signal?.aborted) toast.error('Failed to load stats');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchStats(ctrl.signal);
    return () => ctrl.abort();
  }, [fetchStats]);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchEmails(ctrl.signal);
    return () => ctrl.abort();
  }, [fetchEmails]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => { fetchStats(); fetchEmails(); }, 30_000);
    return () => clearInterval(id);
  }, [autoRefresh, fetchStats, fetchEmails]);

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleSearchInput = (val: string) => {
    setSearchInput(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { setSearch(val); setPage(1); }, 350);
  };

  const setFilter = (setter: (v: string) => void) => (v: string) => {
    setter(v);
    setPage(1);
  };

  const clearFilters = () => {
    setSearch(''); setSearchInput(''); setFilterStatus('');
    setFilterHasBounces(''); setFilterPlaceholder(''); setPage(1);
  };

  const handleBackfill = async () => {
    setBackfillLoading(true);
    try {
      await triggerHrEmailBackfill();
      toast.success('Backfill queued — refresh in a moment');
    } catch {
      toast.error('Failed to queue backfill');
    } finally {
      setBackfillLoading(false);
    }
  };

  const handleImport = async (file: File) => {
    setImporting(true);
    setImportResult(null);
    try {
      const result = await importBrevoCSV(file);
      setImportResult(result);
      toast.success(`Imported ${fmt(result.total_rows)} rows — ${fmt(result.hr_emails_upserted)} emails updated`);
    } catch {
      toast.error('Import failed — check the CSV format and try again');
    } finally {
      setImporting(false);
    }
  };

  const handleValidateMx = async (em: HrEmail) => {
    setValidatingIds((s) => new Set(s).add(em.id));
    try {
      await validateHrEmailMx(em.id);
      toast.success(`MX validation queued for ${em.domain}`);
    } catch {
      toast.error('Failed to queue MX validation');
    } finally {
      setValidatingIds((s) => { const n = new Set(s); n.delete(em.id); return n; });
    }
  };

  const handleMarkInvalid = async (em: HrEmail) => {
    setMarkingInvalidIds((s) => new Set(s).add(em.id));
    try {
      await updateHrEmail(em.id, { validation_status: 'invalid' });
      toast.success('Marked as invalid');
      fetchEmails();
      fetchStats();
    } catch {
      toast.error('Failed to update');
    } finally {
      setMarkingInvalidIds((s) => { const n = new Set(s); n.delete(em.id); return n; });
    }
  };

  const handleRefresh = () => { fetchStats(); fetchEmails(); };

  // ── Chart data ───────────────────────────────────────────────────────────────

  const invalidCount = stats
    ? stats.total_unique - stats.valid_count - stats.bounced_count - stats.fake_count - stats.unknown_count
    : 0;

  const chartData = stats
    ? [
        { name: 'Unknown', count: stats.unknown_count, color: CHART_COLORS.Unknown },
        { name: 'Valid', count: stats.valid_count, color: CHART_COLORS.Valid },
        { name: 'Bounced', count: stats.bounced_count, color: CHART_COLORS.Bounced },
        { name: 'Fake', count: stats.fake_count, color: CHART_COLORS.Fake },
        { name: 'Invalid', count: Math.max(0, invalidCount), color: CHART_COLORS.Invalid },
      ].filter((d) => d.count > 0)
    : [];

  const isEmpty = !loading && (stats?.total_unique ?? 0) === 0;

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">

      {/* ── Header ── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white">HR Email Analysis</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Diagnose and improve HR email quality across all scraped jobs
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleBackfill}
            disabled={backfillLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            {backfillLoading ? <Loader2 size={14} className="animate-spin" /> : <Database size={14} />}
            Backfill Jobs
          </button>
          <button
            onClick={() => setAutoRefresh((p) => !p)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border transition-colors ${
              autoRefresh
                ? 'bg-green-50 border-green-300 text-green-700 dark:bg-green-900/30 dark:border-green-700 dark:text-green-400'
                : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400'
            }`}
          >
            Auto-refresh
          </button>
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="p-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* ── Import Result ── */}
      {importResult && (
        <ImportResultCard
          result={importResult}
          onClose={() => setImportResult(null)}
          onRefresh={handleRefresh}
        />
      )}

      {/* ── CSV Import Section ── */}
      {isEmpty ? (
        /* Empty state: show import CTA prominently */
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-6">
          <div className="text-center mb-5">
            <AtSign size={40} className="mx-auto mb-3 text-gray-300 dark:text-gray-600" />
            <h2 className="text-base font-semibold text-gray-700 dark:text-gray-300 mb-1">No HR email data yet</h2>
            <p className="text-sm text-gray-400 dark:text-gray-500">
              Import your Brevo email log CSV to populate this dashboard, or run a backfill from your jobs data.
            </p>
          </div>
          {importing ? (
            <div className="flex flex-col items-center gap-2 py-6">
              <Loader2 size={28} className="animate-spin text-blue-500" />
              <p className="text-sm text-gray-500 dark:text-gray-400">Importing CSV — this may take a moment…</p>
            </div>
          ) : (
            <CsvDropZone onImport={handleImport} />
          )}
        </div>
      ) : (
        /* Compact import section when data already exists */
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
          <details className="group">
            <summary className="flex items-center gap-2 px-4 py-3 cursor-pointer select-none text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-750 list-none">
              <Upload size={15} className="text-blue-500" />
              Import Brevo CSV
              <span className="text-xs text-gray-400 ml-1 font-normal">— re-import or update from a new export</span>
              <span className="ml-auto text-gray-400 text-xs group-open:hidden">▸ expand</span>
              <span className="ml-auto text-gray-400 text-xs hidden group-open:inline">▾ collapse</span>
            </summary>
            <div className="px-4 pb-4 border-t border-gray-100 dark:border-gray-700">
              {importing ? (
                <div className="flex flex-col items-center gap-2 py-6">
                  <Loader2 size={24} className="animate-spin text-blue-500" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">Importing CSV…</p>
                </div>
              ) : (
                <div className="mt-3">
                  <CsvDropZone onImport={handleImport} />
                </div>
              )}
            </div>
          </details>
        </div>
      )}

      {/* ── Stats Cards (only when data exists) ── */}
      {stats && stats.total_unique > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <StatsCard title="Unique Emails" value={fmt(stats.total_unique)} icon={AtSign} color="blue" />
          <StatsCard title="Valid" value={`${stats.valid_pct}%`} icon={CheckCircle} color="green"
            subtitle={`${fmt(stats.valid_count)} emails`} />
          <StatsCard title="Bounce Rate" value={`${stats.bounce_rate}%`} icon={AlertTriangle} color="orange"
            subtitle={`${fmt(stats.bounced_count)} bounced`} />
          <StatsCard title="Domains w/ Bounces" value={fmt(stats.domains_with_bounces)} icon={ShieldOff} color="orange" />
          <StatsCard title="Fake / Placeholder" value={fmt(stats.fake_count)} icon={XCircle} color="orange"
            subtitle={`${fmt(stats.unknown_count)} unknown`} />
        </div>
      )}

      {/* ── Charts + Send Performance ── */}
      {stats && stats.total_unique > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Quality breakdown chart */}
          {chartData.length > 0 && (
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
              <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-1.5">
                <BarChart2 size={15} />
                Email Quality Breakdown
              </h2>
              <ResponsiveContainer width="100%" height={190}>
                <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => [fmt(v), 'Emails']} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Send performance panel */}
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-1.5">
              <Mail size={15} />
              Send Performance
            </h2>
            <div className="space-y-2.5">
              {[
                {
                  icon: Send,
                  label: 'Total Sends',
                  value: fmt(stats.total_sends),
                  color: 'bg-blue-500',
                },
                {
                  icon: CheckCircle,
                  label: 'Delivered',
                  value: `${fmt(stats.total_delivered)} (${pct(stats.total_delivered, stats.total_sends)})`,
                  color: 'bg-green-500',
                },
                {
                  icon: Eye,
                  label: 'Opened',
                  value: pct(stats.valid_count, stats.total_unique),   // proxy: valid = opened at least once
                  color: 'bg-indigo-500',
                },
                {
                  icon: AlertTriangle,
                  label: 'Hard Bounced',
                  value: `${fmt(stats.bounced_count)} emails`,
                  color: 'bg-red-500',
                },
                {
                  icon: TrendingDown,
                  label: 'Bounce Rate',
                  value: `${stats.bounce_rate}%`,
                  color: 'bg-orange-500',
                },
                {
                  icon: ShieldOff,
                  label: 'Domains Affected',
                  value: fmt(stats.domains_with_bounces),
                  color: 'bg-yellow-500',
                },
              ].map(({ icon: Icon, label, value, color }) => (
                <div key={label} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${color}`} />
                    <Icon size={12} className="text-gray-400" />
                    <span className="text-gray-600 dark:text-gray-400">{label}</span>
                  </div>
                  <span className="font-medium text-gray-800 dark:text-gray-200">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Domain Analysis Table ── */}
      {domainData.length > 0 && (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Domain Analysis</h2>
            <span className="text-xs text-gray-400">sorted by bounce count</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 dark:bg-gray-750 text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  <th className="px-4 py-2 text-left">Domain</th>
                  <th className="px-4 py-2 text-right">Emails</th>
                  <th className="px-4 py-2 text-right">Sends</th>
                  <th className="px-4 py-2 text-right">Bounces</th>
                  <th className="px-4 py-2 text-right">Bounce %</th>
                  <th className="px-4 py-2 text-center">MX</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {domainData.map((row) => (
                  <tr key={row.domain} className="hover:bg-gray-50 dark:hover:bg-gray-750">
                    <td className="px-4 py-2 font-mono text-xs text-gray-700 dark:text-gray-300">{row.domain}</td>
                    <td className="px-4 py-2 text-right text-gray-600 dark:text-gray-400">{fmt(row.email_count)}</td>
                    <td className="px-4 py-2 text-right text-gray-600 dark:text-gray-400">{fmt(row.send_count)}</td>
                    <td className="px-4 py-2 text-right">
                      <span className={row.bounce_count > 0 ? 'text-red-500 font-medium' : 'text-gray-400'}>
                        {fmt(row.bounce_count)}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className={
                        row.bounce_rate > 50
                          ? 'text-red-500 font-semibold'
                          : row.bounce_rate > 20
                          ? 'text-orange-500'
                          : 'text-gray-500'
                      }>
                        {row.bounce_rate > 0 ? `${row.bounce_rate}%` : '—'}
                      </span>
                    </td>
                    <td className="px-4 py-2 flex justify-center">
                      <MxIcon mx={row.mx_valid} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Filters ── */}
      {!isEmpty && (
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            placeholder="Search email or domain…"
            value={searchInput}
            onChange={(e) => handleSearchInput(e.target.value)}
            className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 w-56"
          />
          <select
            value={filterStatus}
            onChange={(e) => setFilter(setFilterStatus)(e.target.value)}
            className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
          >
            <option value="">All Statuses</option>
            <option value="unknown">Unknown</option>
            <option value="valid">Valid</option>
            <option value="bounced">Bounced</option>
            <option value="invalid">Invalid</option>
            <option value="fake">Fake</option>
          </select>
          <select
            value={filterHasBounces}
            onChange={(e) => setFilter(setFilterHasBounces)(e.target.value)}
            className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
          >
            <option value="">Has Bounces: Any</option>
            <option value="yes">Has Bounces: Yes</option>
            <option value="no">Has Bounces: No</option>
          </select>
          <select
            value={filterPlaceholder}
            onChange={(e) => setFilter(setFilterPlaceholder)(e.target.value)}
            className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300"
          >
            <option value="">Placeholder: Any</option>
            <option value="yes">Placeholder: Yes</option>
            <option value="no">Placeholder: No</option>
          </select>
          {(search || filterStatus || filterHasBounces || filterPlaceholder) && (
            <button
              onClick={clearFilters}
              className="px-2 py-1.5 text-sm text-red-600 dark:text-red-400 border border-red-300 dark:border-red-700 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              Clear
            </button>
          )}
        </div>
      )}

      {/* ── Email List Table ── */}
      {!isEmpty && (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 dark:bg-gray-750 text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  <th className="px-4 py-2 text-left">Email / Domain</th>
                  <th className="px-4 py-2 text-right">Jobs</th>
                  <th className="px-4 py-2 text-right">Sends</th>
                  <th className="px-4 py-2 text-right">Delivered</th>
                  <th className="px-4 py-2 text-right">Hard Bounces</th>
                  <th className="px-4 py-2 text-left">Last Bounce Reason</th>
                  <th className="px-4 py-2 text-center">Status</th>
                  <th className="px-4 py-2 text-center">MX</th>
                  <th className="px-4 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                {emails.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-4 py-10 text-center text-gray-400 dark:text-gray-500 text-sm">
                      No emails match your filters
                    </td>
                  </tr>
                )}
                {emails.map((em) => (
                  <tr key={em.id} className="hover:bg-gray-50 dark:hover:bg-gray-750">
                    <td className="px-4 py-2">
                      <div
                        className="font-mono text-xs text-gray-700 dark:text-gray-200 truncate max-w-[220px]"
                        title={em.email}
                      >
                        {em.email}
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5">{em.domain}</div>
                    </td>
                    <td className="px-4 py-2 text-right text-gray-600 dark:text-gray-400">{fmt(em.job_count)}</td>
                    <td className="px-4 py-2 text-right text-gray-600 dark:text-gray-400">{fmt(em.send_count)}</td>
                    <td className="px-4 py-2 text-right text-gray-600 dark:text-gray-400">{fmt(em.delivered_count)}</td>
                    <td className="px-4 py-2 text-right">
                      <span className={em.hard_bounce_count > 0 ? 'text-red-500 font-medium' : 'text-gray-400'}>
                        {fmt(em.hard_bounce_count)}
                      </span>
                    </td>
                    <td className="px-4 py-2 max-w-[180px]">
                      {em.last_bounce_reason ? (
                        <span className="text-xs text-red-400 truncate block" title={em.last_bounce_reason}>
                          {em.last_bounce_reason}
                        </span>
                      ) : em.last_bounce_type ? (
                        <span className="text-xs text-orange-400 capitalize">{em.last_bounce_type}</span>
                      ) : (
                        <span className="text-xs text-gray-300 dark:text-gray-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-center">
                      <Badge status={em.validation_status} />
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex justify-center">
                        <MxIcon mx={em.mx_valid} />
                      </div>
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => handleValidateMx(em)}
                          disabled={validatingIds.has(em.id)}
                          title="Check MX DNS record for this domain"
                          className="px-2 py-1 text-xs rounded border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 disabled:opacity-50 flex items-center gap-1"
                        >
                          {validatingIds.has(em.id) ? <Loader2 size={11} className="animate-spin" /> : null}
                          MX Check
                        </button>
                        {em.validation_status !== 'invalid' && (
                          <button
                            onClick={() => handleMarkInvalid(em)}
                            disabled={markingInvalidIds.has(em.id)}
                            title="Mark this email as invalid"
                            className="px-2 py-1 text-xs rounded border border-red-300 dark:border-red-700 text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 flex items-center gap-1"
                          >
                            {markingInvalidIds.has(em.id) ? <Loader2 size={11} className="animate-spin" /> : null}
                            Invalid
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 text-sm text-gray-600 dark:text-gray-400">
            <div className="flex items-center gap-2">
              <span className="text-xs">Rows per page:</span>
              {PAGE_SIZES.map((s) => (
                <button
                  key={s}
                  onClick={() => { setPageSize(s); setPage(1); }}
                  className={`px-2 py-0.5 rounded text-xs ${
                    pageSize === s
                      ? 'bg-blue-600 text-white'
                      : 'hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 text-xs">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                ← Prev
              </button>
              <span>Page {page}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={emails.length < pageSize}
                className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                Next →
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
