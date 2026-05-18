'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  Ban, ExternalLink, FileText, Loader2, Mail,
  RefreshCw, Send, Sparkles, X, ChevronUp, ChevronDown,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import toast from 'react-hot-toast';
import StatusBadge from '../../components/StatusBadge';
import CoverLetterModal from '../../components/CoverLetterModal';
import BulkSendModal from '../../components/BulkSendModal';
import {
  bulkGenerateCovers, generateCoverLetter, getCandidates,
  getJobIds, getJobs, getJobsCount, updateJobStatus, setJobHrEmail,
  type BulkSendResult, type Candidate, type Job,
} from '../../lib/api';

// ─── Constants ───────────────────────────────────────────────────────────────

const PORTALS    = [
  'naukri', 'indeed', 'linkedin', 'shine', 'internshala',
  'remoteok', 'weworkremotely', 'workingnomads', 'jobspresso',
];
const STATUSES   = ['new', 'scoring', 'filtered', 'pending_approval', 'cover_generated', 'sending', 'sent', 'applied', 'bounced', 'ignored', 'error'];
const PAGE_SIZES = [5, 10, 20, 50, 100] as const;

interface JobFilters {
  search: string;
  status: string;
  portal: string;
  job_type: string;
  has_hr_email: '' | 'yes' | 'no';
  has_cover: '' | 'yes' | 'no';
  min_score: number;      // 0–100; divided by 100 before API call
  scraped_after: string;  // ISO date string e.g. '2026-04-10', or ''
  posted_after: string;   // ISO date string e.g. '2026-04-10', or ''
  sort_by: 'scraped_at' | 'relevance_score' | 'company' | 'job_title';
  sort_dir: 'asc' | 'desc';
  page: number;
  page_size: number;
}

const DEFAULT_FILTERS: JobFilters = {
  search: '', status: '', portal: '', job_type: '', has_hr_email: '', has_cover: '',
  min_score: 0, scraped_after: '', posted_after: '', sort_by: 'scraped_at', sort_dir: 'desc', page: 1, page_size: 20,
};

function todayISO(): string { return new Date().toISOString().split('T')[0]; }
function daysAgoISO(n: number): string { return new Date(Date.now() - n * 86_400_000).toISOString().split('T')[0]; }

const PRESETS: { label: string; filters: () => Partial<JobFilters> }[] = [
  {
    label: 'Ready to Apply',
    // Cover ready + HR email known + exclude already-sent/applied statuses
    filters: () => ({ has_hr_email: 'yes', has_cover: 'yes', status: 'cover_generated' }),
  },
];

const ROW_STATUS_BG: Record<string, string> = {
  applied:          'bg-green-50/60 dark:bg-green-900/10',
  sent:             'bg-indigo-50/40 dark:bg-indigo-900/10',
  cover_generated:  'bg-blue-50/40 dark:bg-blue-900/10',
  pending_approval: 'bg-amber-50/40 dark:bg-amber-900/10',
  bounced:          'bg-red-50/40 dark:bg-red-900/10',
  error:            'bg-red-50/40 dark:bg-red-900/10',
  ignored:          'opacity-50',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function buildApiParams(f: JobFilters, extra?: Record<string, unknown>): Record<string, unknown> {
  const p: Record<string, unknown> = {
    page: f.page, page_size: f.page_size,
    sort_by: f.sort_by, sort_dir: f.sort_dir,
  };
  if (f.search)               p.search = f.search;
  if (f.status)               p.status = f.status;
  if (f.portal)               p.portal = f.portal;
  if (f.job_type)             p.job_type = f.job_type;
  if (f.has_hr_email === 'yes') p.has_hr_email = true;
  if (f.has_hr_email === 'no')  p.has_hr_email = false;
  if (f.has_cover === 'yes')  p.has_cover = true;
  if (f.has_cover === 'no')   p.has_cover = false;
  if (f.min_score > 0)        p.min_score = f.min_score / 100;
  if (f.scraped_after)        p.scraped_after = f.scraped_after;
  if (f.posted_after)         p.posted_after  = f.posted_after;
  return { ...p, ...extra };
}

function buildCountParams(f: JobFilters): Record<string, unknown> {
  const { page: _p, page_size: _ps, sort_by: _sb, sort_dir: _sd, ...rest } = buildApiParams(f) as Record<string, unknown>;
  void _p; void _ps; void _sb; void _sd;
  return rest;
}

function fmtSalary(job: Job): string | undefined {
  if (!job.salary_min) return undefined;
  const cur = job.salary_currency || '₹';
  const min = job.salary_min.toLocaleString('en-IN');
  const max = job.salary_max ? `–${job.salary_max.toLocaleString('en-IN')}` : '';
  return `${cur}${min}${max}`;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SortTh({
  col, label, sort_by, sort_dir, onSort,
}: {
  col: JobFilters['sort_by'];
  label: string;
  sort_by: JobFilters['sort_by'];
  sort_dir: JobFilters['sort_dir'];
  onSort: (col: JobFilters['sort_by']) => void;
}) {
  const active = sort_by === col;
  return (
    <th
      className="px-4 py-3 font-medium cursor-pointer select-none group hover:text-gray-900 dark:hover:text-gray-100"
      onClick={() => onSort(col)}
    >
      <span className="flex items-center gap-1">
        {label}
        {active ? (
          sort_dir === 'desc' ? <ChevronDown size={13} /> : <ChevronUp size={13} />
        ) : (
          <ChevronDown size={13} className="opacity-0 group-hover:opacity-30" />
        )}
      </span>
    </th>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function JobsPage() {
  // Data
  const [jobs, setJobs]             = useState<Job[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading]       = useState(true);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [activeCandidateId, setActiveCandidateId] = useState('');

  // Filters (debounced search)
  const [filters, setFilters]       = useState<JobFilters>(DEFAULT_FILTERS);
  const [searchInput, setSearchInput] = useState('');

  // Selection
  const [selected, setSelected]               = useState<Set<string>>(new Set());
  const [selectAllMatching, setSelectAllMatching] = useState(false);
  const selectAllCheckboxRef                  = useRef<HTMLInputElement>(null);

  // UI
  const [autoRefresh, setAutoRefresh]         = useState(false);
  const [coverModalJob, setCoverModalJob]     = useState<Job | null>(null);
  const [bulkModalJobs, setBulkModalJobs]     = useState<Job[] | null>(null);
  const [bulkGenLoading, setBulkGenLoading]   = useState(false);

  // HR email inline editing — keyed by job id
  const [hrEmailEdit, setHrEmailEdit]       = useState<Record<string, string>>({});
  const [hrEmailSaving, setHrEmailSaving]   = useState<Record<string, boolean>>({});

  // ── Candidate bootstrap ──────────────────────────────────────────────────
  useEffect(() => {
    getCandidates().then(cs => {
      setCandidates(cs);
      const stored = typeof window !== 'undefined' ? localStorage.getItem('activeCandidateId') : null;
      const valid = stored && cs.find(c => c.id === stored);
      setActiveCandidateId(valid ? stored! : (cs[0]?.id ?? ''));
    }).catch(() => {});
  }, []);

  const handleCandidateChange = (id: string) => {
    setActiveCandidateId(id);
    if (typeof window !== 'undefined') localStorage.setItem('activeCandidateId', id);
  };

  // ── Debounce search input ────────────────────────────────────────────────
  useEffect(() => {
    const t = setTimeout(() => {
      setFilters(f => ({ ...f, search: searchInput, page: 1 }));
    }, 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  // ── Fetch jobs — abort any previous in-flight request when filters change ──
  const abortRef = useRef<AbortController | null>(null);

  const fetchJobs = useCallback(async () => {
    // Cancel the previous request if it hasn't finished yet
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    try {
      const params = buildApiParams(filters);
      const countParams = buildCountParams(filters);
      const [data, countData] = await Promise.all([
        getJobs(params, controller.signal),
        getJobsCount(countParams, controller.signal),
      ]);
      setJobs(data);
      setTotalCount(countData.count);
    } catch (err: unknown) {
      // Ignore AbortError — it's expected when filters change rapidly
      if (err instanceof Error && err.name !== 'AbortError' && err.name !== 'CanceledError') {
        toast.error('Failed to load jobs');
      }
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  // ── Auto-refresh ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(fetchJobs, 30_000);
    return () => clearInterval(id);
  }, [autoRefresh, fetchJobs]);

  // ── Select-all indeterminate state ───────────────────────────────────────
  const allPageSelected  = jobs.length > 0 && jobs.every(j => selected.has(j.id));
  const somePageSelected = jobs.some(j => selected.has(j.id)) && !allPageSelected;

  useEffect(() => {
    if (selectAllCheckboxRef.current) {
      selectAllCheckboxRef.current.indeterminate = somePageSelected;
    }
  }, [somePageSelected]);

  // ── Selection handlers ───────────────────────────────────────────────────
  const toggleSelect = (id: string) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
    setSelectAllMatching(false);
  };

  const handleSelectAllPage = () => {
    const next = new Set(selected);
    if (allPageSelected) {
      jobs.forEach(j => next.delete(j.id));
      setSelectAllMatching(false);
    } else {
      jobs.forEach(j => next.add(j.id));
    }
    setSelected(next);
  };

  const handleSelectAllMatching = () => {
    const next = new Set(selected);
    jobs.forEach(j => next.add(j.id));
    setSelected(next);
    setSelectAllMatching(true);
  };

  const clearSelection = () => {
    setSelected(new Set());
    setSelectAllMatching(false);
  };

  // ── Get effective IDs for bulk actions ───────────────────────────────────
  const getEffectiveIds = async (): Promise<string[]> => {
    if (!selectAllMatching) return [...selected];
    // Use /jobs/ids which has no page_size cap (returns up to 5000 IDs)
    return getJobIds(buildCountParams(filters));
  };

  // ── Sorting ──────────────────────────────────────────────────────────────
  const handleSort = (col: JobFilters['sort_by']) => {
    setFilters(f => ({
      ...f,
      sort_by: col,
      sort_dir: f.sort_by === col && f.sort_dir === 'desc' ? 'asc' : 'desc',
      page: 1,
    }));
  };

  const applyPreset = (preset: () => Partial<JobFilters>) =>
    setFilters(f => ({ ...f, ...preset(), page: 1 }));

  // ── Per-row actions ──────────────────────────────────────────────────────
  const handleRowSend = (job: Job) => {
    if (!job.cover_letter) {
      toast.error('Generate a cover letter first', { icon: '✏️' });
      return;
    }
    setCoverModalJob(job);
  };

  const handleQuickGenerate = async (jobId: string) => {
    if (!activeCandidateId) {
      toast.error('Select a candidate first');
      return;
    }
    try {
      await generateCoverLetter(jobId, activeCandidateId);
      toast.success('Cover letter generation queued');
    } catch {
      toast.error('Failed to queue generation');
    }
  };

  // ── Bulk actions ─────────────────────────────────────────────────────────
  const handleBulkIgnore = async () => {
    const ids = await getEffectiveIds();
    await Promise.all(ids.map(id => updateJobStatus(id, 'ignored')));
    toast.success(`Ignored ${ids.length} jobs`);
    clearSelection();
    fetchJobs();
  };

  const handleBulkGenerateCovers = async () => {
    if (!activeCandidateId) { toast.error('Select a candidate first'); return; }
    const ids = await getEffectiveIds();
    setBulkGenLoading(true);
    try {
      const r = await bulkGenerateCovers(ids, activeCandidateId);
      toast.success(`Queued cover generation for ${r.queued} jobs`);
      clearSelection();
    } catch {
      toast.error('Bulk generation failed');
    } finally {
      setBulkGenLoading(false);
    }
  };

  const handleBulkSend = async () => {
    if (!activeCandidateId) { toast.error('Select a candidate first'); return; }
    const ids = await getEffectiveIds();
    // Fetch job objects so BulkSendModal can show readiness details
    const selectedJobs = jobs.filter(j => ids.includes(j.id));
    // If selectAllMatching, some jobs may not be on current page — fetch them
    if (selectAllMatching) {
      // ids already fetched above — filter jobs on current page + re-fetch full list
      const allJobs = await getJobs({ ...buildApiParams(filters), page: 1, page_size: Math.min(totalCount, 100) });
      setBulkModalJobs(allJobs);
    } else {
      setBulkModalJobs(selectedJobs);
    }
  };

  const handleBulkSendQueued = (result: BulkSendResult) => {
    void result;
    clearSelection();
    fetchJobs();
  };

  // ── HR email inline save ─────────────────────────────────────────────────
  const handleSaveHrEmail = async (jobId: string) => {
    const email = (hrEmailEdit[jobId] ?? '').trim();
    if (!email) return;
    setHrEmailSaving(s => ({ ...s, [jobId]: true }));
    try {
      const updated = await setJobHrEmail(jobId, email);
      setJobs(prev => prev.map(j => j.id === jobId ? { ...j, hr_email: updated.hr_email } : j));
      setHrEmailEdit(e => { const n = { ...e }; delete n[jobId]; return n; });
      toast.success('HR email saved');
    } catch {
      toast.error('Failed to save HR email');
    } finally {
      setHrEmailSaving(s => ({ ...s, [jobId]: false }));
    }
  };

  // ── Effective count for toolbar labels ───────────────────────────────────
  const effectiveCount = selectAllMatching ? totalCount : selected.size;
  const totalPages = Math.ceil(totalCount / filters.page_size) || 1;

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">

      {/* ── Header row ────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Jobs</h1>
        <div className="flex items-center gap-2 ml-auto">
          {/* Candidate selector */}
          {candidates.length > 0 && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-500 dark:text-gray-400 whitespace-nowrap">Apply as:</span>
              <select
                value={activeCandidateId}
                onChange={e => handleCandidateChange(e.target.value)}
                className="rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-2.5 py-1.5 text-sm"
              >
                {candidates.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
          )}
          {/* Auto-refresh */}
          <button
            onClick={() => setAutoRefresh(v => !v)}
            title={autoRefresh ? 'Auto-refresh on (30s)' : 'Auto-refresh off'}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs border ${
              autoRefresh
                ? 'border-green-400 dark:border-green-600 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400'
                : 'border-gray-300 dark:border-gray-700 text-gray-500 dark:text-gray-400'
            }`}
          >
            <RefreshCw size={12} className={autoRefresh ? 'animate-spin' : ''} />
            {autoRefresh ? 'Auto' : 'Refresh'}
          </button>
          <button
            onClick={fetchJobs}
            className="p-1.5 rounded-lg border border-gray-300 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"
            title="Refresh now"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* ── Filters panel ─────────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 space-y-3">

        {/* Row 1: Search + dropdown filters */}
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            placeholder="Search title, company, location, HR email…"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            className="text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5 flex-1 min-w-[200px]"
          />
          <select
            value={filters.status}
            onChange={e => setFilters(f => ({ ...f, status: e.target.value, page: 1 }))}
            className="text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
          >
            <option value="">All Statuses</option>
            {STATUSES.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
          </select>
          <select
            value={filters.portal}
            onChange={e => setFilters(f => ({ ...f, portal: e.target.value, page: 1 }))}
            className="text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
          >
            <option value="">All Portals</option>
            {PORTALS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <select
            value={filters.has_hr_email}
            onChange={e => setFilters(f => ({ ...f, has_hr_email: e.target.value as JobFilters['has_hr_email'], page: 1 }))}
            className="text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
          >
            <option value="">Any HR Email</option>
            <option value="yes">Has HR Email</option>
            <option value="no">No HR Email</option>
          </select>
          <select
            value={filters.job_type}
            onChange={e => setFilters(f => ({ ...f, job_type: e.target.value, page: 1 }))}
            className="text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
          >
            <option value="">Any Job Type</option>
            <option value="full-time">Full-time</option>
            <option value="contract">Contract</option>
            <option value="part-time">Part-time</option>
            <option value="internship">Internship</option>
          </select>
          <select
            value={filters.scraped_after}
            onChange={e => setFilters(f => ({ ...f, scraped_after: e.target.value, page: 1 }))}
            className="text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
          >
            <option value="">Any time</option>
            <option value={todayISO()}>Today</option>
            <option value={daysAgoISO(7)}>Last 7 days</option>
            <option value={daysAgoISO(30)}>Last 30 days</option>
            <option value={daysAgoISO(60)}>Last 2 months</option>
          </select>
          <select
            value={filters.posted_after}
            onChange={e => setFilters(f => ({ ...f, posted_after: e.target.value, page: 1 }))}
            className="text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
          >
            <option value="">Posted: Any time</option>
            <option value={todayISO()}>Posted today</option>
            <option value={daysAgoISO(7)}>Posted last 7 days</option>
            <option value={daysAgoISO(30)}>Posted last 30 days</option>
            <option value={daysAgoISO(60)}>Posted last 2 months</option>
            <option value={daysAgoISO(90)}>Posted last 3 months</option>
          </select>
        </div>

        {/* Row 2: Presets */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5">
            {PRESETS.map(p => (
              <button
                key={p.label}
                onClick={() => applyPreset(p.filters)}
                className="px-2.5 py-1 rounded-full text-xs border border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-blue-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                {p.label}
              </button>
            ))}

            {JSON.stringify(filters) !== JSON.stringify(DEFAULT_FILTERS) && (
              <button
                onClick={() => { setSearchInput(''); setFilters(DEFAULT_FILTERS); }}
                className="px-2.5 py-1 rounded-full text-xs border border-red-300 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Bulk action toolbar ────────────────────────────────────────────── */}
      {(selected.size > 0 || selectAllMatching) && (
        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl">
          <span className="text-sm text-blue-700 dark:text-blue-300 font-medium">
            {selectAllMatching ? `All ${totalCount} matching` : `${selected.size} selected`}
          </span>
          {!selectAllMatching && totalCount > jobs.length && (
            <button
              onClick={handleSelectAllMatching}
              className="text-xs text-blue-600 dark:text-blue-400 underline underline-offset-2"
            >
              Select all {totalCount} matching
            </button>
          )}
          <div className="flex-1" />
          <button
            onClick={handleBulkGenerateCovers}
            disabled={bulkGenLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400 text-xs font-medium hover:bg-purple-200 dark:hover:bg-purple-900/50 disabled:opacity-50"
          >
            {bulkGenLoading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            Generate Covers ({effectiveCount})
          </button>
          <button
            onClick={handleBulkSend}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700"
          >
            <Send size={12} />
            Send HR ({effectiveCount})
          </button>
          <button
            onClick={handleBulkIgnore}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400 text-xs font-medium hover:bg-red-200 dark:hover:bg-red-900/40"
          >
            <Ban size={12} />
            Ignore ({effectiveCount})
          </button>
          <button
            onClick={clearSelection}
            className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-gray-500 dark:text-gray-400 text-xs hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <X size={12} /> Clear
          </button>
        </div>
      )}

      {/* ── Jobs table ────────────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="animate-spin text-blue-600" size={24} />
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-12 text-gray-400">No jobs found</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
                <th className="px-4 py-3 w-8">
                  <input
                    ref={selectAllCheckboxRef}
                    type="checkbox"
                    checked={allPageSelected}
                    onChange={handleSelectAllPage}
                    className="rounded"
                  />
                </th>
                <SortTh col="job_title"  label="Job Title"  sort_by={filters.sort_by} sort_dir={filters.sort_dir} onSort={handleSort} />
                <SortTh col="company"    label="Company"    sort_by={filters.sort_by} sort_dir={filters.sort_dir} onSort={handleSort} />
                <th className="px-4 py-3 font-medium">Location</th>
                <th className="px-4 py-3 font-medium">Portal</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium w-14" title="Cover letter">Cover</th>
                <th className="px-4 py-3 font-medium w-20">HR Email</th>
                <SortTh col="relevance_score" label="Score" sort_by={filters.sort_by} sort_dir={filters.sort_dir} onSort={handleSort} />
                <SortTh col="scraped_at"  label="Scraped"   sort_by={filters.sort_by} sort_dir={filters.sort_dir} onSort={handleSort} />
                <th className="px-4 py-3 font-medium">Posted</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
              {jobs.map(job => {
                const isSelected = selected.has(job.id);
                const salary = fmtSalary(job);
                return (
                  <tr
                    key={job.id}
                    className={`transition-colors ${
                      isSelected
                        ? 'bg-blue-50 dark:bg-blue-900/15'
                        : (ROW_STATUS_BG[job.status] ?? 'hover:bg-gray-50 dark:hover:bg-gray-800/50')
                    }`}
                  >
                    {/* Checkbox */}
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelect(job.id)}
                        className="rounded"
                      />
                    </td>

                    {/* Job Title */}
                    <td className="px-4 py-3 max-w-[200px]">
                      <Link
                        href={`/jobs/${job.id}`}
                        className="font-medium text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 block truncate"
                      >
                        {job.job_title}
                      </Link>
                      {job.experience_required && (
                        <span className="text-xs text-gray-400 dark:text-gray-500">{job.experience_required}</span>
                      )}
                    </td>

                    {/* Company */}
                    <td className="px-4 py-3 max-w-[140px]">
                      <span
                        className="text-gray-700 dark:text-gray-300 truncate block"
                        title={salary ? `${job.company} · ${salary}` : job.company}
                      >
                        {job.company}
                        {salary && <span className="ml-1 text-xs text-green-600 dark:text-green-400">₹</span>}
                      </span>
                    </td>

                    {/* Location */}
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400 truncate max-w-[110px]">
                      {job.location || '—'}
                    </td>

                    {/* Portal */}
                    <td className="px-4 py-3"><StatusBadge status={job.source_portal} /></td>

                    {/* Status */}
                    <td className="px-4 py-3"><StatusBadge status={job.status} /></td>

                    {/* Cover indicator */}
                    <td className="px-4 py-3 text-center">
                      {job.cover_letter ? (
                        <span title="Cover letter ready" className="flex justify-center">
                          <FileText size={14} className="text-blue-500 dark:text-blue-400" />
                        </span>
                      ) : (
                        <span title="No cover letter" className="flex justify-center">
                          <FileText size={14} className="text-gray-300 dark:text-gray-600" />
                        </span>
                      )}
                    </td>

                    {/* HR Email */}
                    <td className="px-4 py-3">
                      {job.hr_email ? (
                        <span className="flex items-center gap-1 text-green-600 dark:text-green-400" title={job.hr_email}>
                          <Mail size={12} /> Found
                        </span>
                      ) : hrEmailEdit[job.id] !== undefined ? (
                        <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                          <input
                            autoFocus
                            type="email"
                            value={hrEmailEdit[job.id]}
                            onChange={e => setHrEmailEdit(s => ({ ...s, [job.id]: e.target.value }))}
                            onKeyDown={e => {
                              if (e.key === 'Enter') handleSaveHrEmail(job.id);
                              if (e.key === 'Escape') setHrEmailEdit(s => { const n = { ...s }; delete n[job.id]; return n; });
                            }}
                            placeholder="hr@company.com"
                            className="w-36 text-xs px-1.5 py-1 bg-white dark:bg-gray-800 border border-blue-400 dark:border-blue-600 rounded text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                          <button
                            onClick={() => handleSaveHrEmail(job.id)}
                            disabled={hrEmailSaving[job.id]}
                            className="p-1 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white"
                            title="Save HR email"
                          >
                            {hrEmailSaving[job.id] ? <Loader2 size={10} className="animate-spin" /> : <Mail size={10} />}
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={e => { e.stopPropagation(); setHrEmailEdit(s => ({ ...s, [job.id]: '' })); }}
                          className="text-xs text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 transition-colors flex items-center gap-0.5"
                          title="Set HR email manually"
                        >
                          <Mail size={11} /> Set
                        </button>
                      )}
                    </td>

                    {/* Score */}
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400 font-mono text-xs">
                      {job.relevance_score != null ? `${(job.relevance_score * 100).toFixed(0)}%` : '—'}
                    </td>

                    {/* Scraped */}
                    <td className="px-4 py-3 text-gray-400 dark:text-gray-500 text-xs">
                      {job.scraped_at
                        ? formatDistanceToNow(new Date(job.scraped_at), { addSuffix: true })
                        : '—'}
                    </td>

                    {/* Posted */}
                    <td className="px-4 py-3 text-gray-400 dark:text-gray-500 text-xs">
                      {job.posted_date
                        ? <span title={new Date(job.posted_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}>
                            {formatDistanceToNow(new Date(job.posted_date), { addSuffix: true })}
                          </span>
                        : '—'}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        {/* Send button */}
                        <button
                          onClick={() => handleRowSend(job)}
                          title={
                            !job.cover_letter ? 'Generate cover letter first'
                            : !job.hr_email   ? 'No HR email — can override in modal'
                            :                   'Send application'
                          }
                          className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
                            job.cover_letter && job.hr_email
                              ? 'bg-blue-600 text-white hover:bg-blue-700'
                              : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                          }`}
                        >
                          <Send size={11} />
                          Send
                        </button>

                        {/* Generate cover icon */}
                        <button
                          onClick={() => handleQuickGenerate(job.id)}
                          title="Queue cover letter generation"
                          className="p-1 rounded text-gray-400 hover:text-purple-600 dark:hover:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-900/20 transition-colors"
                        >
                          <Sparkles size={13} />
                        </button>

                        {/* External link */}
                        <a
                          href={job.job_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1 rounded text-blue-400 hover:text-blue-600 dark:hover:text-blue-300"
                          title="Open job listing"
                        >
                          <ExternalLink size={13} />
                        </a>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Count + Pagination ────────────────────────────────────────────── */}
      <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
        <span>{totalCount.toLocaleString()} job{totalCount !== 1 ? 's' : ''} matching filters</span>
        <div className="flex items-center gap-3">
          {/* Page size selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">Rows:</span>
            <select
              value={filters.page_size}
              onChange={e => setFilters(f => ({ ...f, page_size: Number(e.target.value), page: 1 }))}
              className="rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-2 py-1 text-xs text-gray-700 dark:text-gray-300"
            >
              {PAGE_SIZES.map(n => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
          {/* Prev / page indicator / Next */}
          <button
            onClick={() => setFilters(f => ({ ...f, page: Math.max(1, f.page - 1) }))}
            disabled={filters.page === 1}
            className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Previous
          </button>
          <span>Page {filters.page} of {totalPages}</span>
          <button
            onClick={() => setFilters(f => ({ ...f, page: f.page + 1 }))}
            disabled={filters.page >= totalPages}
            className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700 disabled:opacity-40 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Next
          </button>
        </div>
      </div>

      {/* ── Modals ────────────────────────────────────────────────────────── */}
      {coverModalJob && activeCandidateId && (
        <CoverLetterModal
          job={coverModalJob}
          candidateId={activeCandidateId}
          onClose={() => setCoverModalJob(null)}
          onSent={() => { setCoverModalJob(null); fetchJobs(); }}
        />
      )}

      {bulkModalJobs && activeCandidateId && (
        <BulkSendModal
          jobs={bulkModalJobs}
          candidateId={activeCandidateId}
          onClose={() => setBulkModalJobs(null)}
          onQueued={handleBulkSendQueued}
        />
      )}
    </div>
  );
}
