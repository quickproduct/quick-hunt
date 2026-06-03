'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  Ban, Building2, ExternalLink, FileText, Loader2, Mail,
  RefreshCw, Send, X, ChevronUp, ChevronDown,
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import toast from 'react-hot-toast';
import StatusBadge from '../../components/StatusBadge';
import CoverLetterModal from '../../components/CoverLetterModal';
import BulkSendModal from '../../components/BulkSendModal';
import {
  getCandidates, getConsultingJobIds, getConsultingJobs, getConsultingJobsCount,
  getJobs, getConsultingScrapeStatus, setJobHrEmail, triggerConsultingScrape, updateJobStatus,
  type BulkSendResult, type Candidate, type Job, type ConsultingScrapeStatus,
} from '../../lib/api';

// ─── Constants ────────────────────────────────────────────────────────────────

const STATUSES   = ['new', 'scoring', 'filtered', 'pending_approval', 'cover_generated', 'sending', 'sent', 'applied', 'bounced', 'ignored', 'error'];
const PAGE_SIZES = [5, 10, 20, 50, 100] as const;

interface JobFilters {
  search: string;
  status: string;
  has_hr_email: '' | 'yes' | 'no';
  has_cover: '' | 'yes' | 'no';
  min_score: number;
  scraped_after: string;
  sort_by: 'scraped_at' | 'relevance_score' | 'company' | 'job_title';
  sort_dir: 'asc' | 'desc';
  page: number;
  page_size: number;
}

const DEFAULT_FILTERS: JobFilters = {
  search: '', status: '', has_hr_email: '', has_cover: '',
  min_score: 0, scraped_after: '',
  sort_by: 'scraped_at', sort_dir: 'desc', page: 1, page_size: 20,
};

function daysAgoISO(n: number): string { return new Date(Date.now() - n * 86_400_000).toISOString().split('T')[0]; }
function todayISO(): string { return new Date().toISOString().split('T')[0]; }

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
  if (f.has_hr_email === 'yes') p.has_hr_email = true;
  if (f.has_hr_email === 'no')  p.has_hr_email = false;
  if (f.has_cover === 'yes')  p.has_cover = true;
  if (f.has_cover === 'no')   p.has_cover = false;
  if (f.min_score > 0)        p.min_score = f.min_score / 100;
  if (f.scraped_after)        p.scraped_after = f.scraped_after;
  return { ...p, ...extra };
}

function buildCountParams(f: JobFilters): Record<string, unknown> {
  const { page: _p, page_size: _ps, sort_by: _sb, sort_dir: _sd, ...rest } = buildApiParams(f) as Record<string, unknown>;
  void _p; void _ps; void _sb; void _sd;
  return rest;
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

export default function ConsultingJobsPage() {
  // Data
  const [jobs, setJobs]             = useState<Job[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading]       = useState(true);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [activeCandidateId, setActiveCandidateId] = useState('');

  // Filters
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
  const [scrapeLoading, setScrapeLoading]     = useState(false);
  const [scrapeStatus, setScrapeStatus]       = useState<ConsultingScrapeStatus | null>(null);

  // HR email inline editing
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

  // ── Debounce search ──────────────────────────────────────────────────────
  useEffect(() => {
    const t = setTimeout(() => {
      setFilters(f => ({ ...f, search: searchInput, page: 1 }));
    }, 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  // ── Fetch jobs ───────────────────────────────────────────────────────────
  const abortRef = useRef<AbortController | null>(null);

  const fetchJobs = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    try {
      const params = buildApiParams(filters);
      const countParams = buildCountParams(filters);
      const [data, countData] = await Promise.all([
        getConsultingJobs(params),
        getConsultingJobsCount(countParams),
      ]);
      setJobs(data);
      setTotalCount(countData.count);
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== 'AbortError' && err.name !== 'CanceledError') {
        toast.error('Failed to load Consulting jobs');
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

  const effectiveCount = selectAllMatching ? totalCount : selected.size;
  const totalPages = Math.max(1, Math.ceil(totalCount / filters.page_size));

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
    jobs.forEach(j => selected.add(j.id));
    setSelected(new Set(selected));
    setSelectAllMatching(true);
  };

  const clearSelection = () => {
    setSelected(new Set());
    setSelectAllMatching(false);
  };

  const getEffectiveIds = async (): Promise<string[]> => {
    if (!selectAllMatching) return [...selected];
    return getConsultingJobIds(buildCountParams(filters));
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

  // ── Row actions ──────────────────────────────────────────────────────────
  const handleRowSend = (job: Job) => {
    setCoverModalJob(job);
  };

  // ── Bulk actions ─────────────────────────────────────────────────────────
  const handleBulkIgnore = async () => {
    const ids = await getEffectiveIds();
    await Promise.all(ids.map(id => updateJobStatus(id, 'ignored')));
    toast.success(`Ignored ${ids.length} jobs`);
    clearSelection();
    fetchJobs();
  };

  const handleBulkSend = async () => {
    if (!activeCandidateId) { toast.error('Select a candidate first'); return; }
    const ids = await getEffectiveIds();
    const selectedJobs = jobs.filter(j => ids.includes(j.id));
    if (selectAllMatching) {
      const allJobs = await getJobs({ ...buildApiParams(filters), page: 1, page_size: Math.min(totalCount, 100), consulting_only: true });
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
    if (!email) { setHrEmailEdit(s => { const n = { ...s }; delete n[jobId]; return n; }); return; }
    setHrEmailSaving(s => ({ ...s, [jobId]: true }));
    try {
      await setJobHrEmail(jobId, email);
      setHrEmailEdit(s => { const n = { ...s }; delete n[jobId]; return n; });
      fetchJobs();
      toast.success('HR email saved');
    } catch {
      toast.error('Failed to save HR email');
    } finally {
      setHrEmailSaving(s => ({ ...s, [jobId]: false }));
    }
  };

  // ── Poll Consulting scrape status ────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const s = await getConsultingScrapeStatus();
        if (cancelled) return;
        setScrapeStatus(s);
      } catch {
        // swallow; status is best-effort UI
      }
    };
    tick(); // immediate
    const id = setInterval(tick, 3000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Auto-refresh the jobs table once when a scrape finishes.
  const prevInFlightRef = useRef(false);
  useEffect(() => {
    const wasInFlight = prevInFlightRef.current;
    const nowInFlight = !!scrapeStatus?.in_flight;
    if (wasInFlight && !nowInFlight) {
      fetchJobs();
      toast.success('Consulting scrape finished');
    }
    prevInFlightRef.current = nowInFlight;
  }, [scrapeStatus?.in_flight, fetchJobs]);

  // ── Trigger Consulting scrape ────────────────────────────────────────────────────
  const handleTriggerScrape = async () => {
    if (scrapeStatus?.in_flight) {
      toast.error('A scrape is already running');
      return;
    }
    setScrapeLoading(true);
    try {
      await triggerConsultingScrape(activeCandidateId || undefined);
      toast.success('Consulting scrape queued — fanning out per-company tasks');
      // refresh status quickly so the button flips disabled
      try { setScrapeStatus(await getConsultingScrapeStatus()); } catch {}
    } catch (err: unknown) {
      // axios error shape — check 409
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        toast.error('Scrape already running');
      } else {
        toast.error('Failed to trigger Consulting scrape');
      }
    } finally {
      setScrapeLoading(false);
    }
  };

  const isScraping = !!scrapeStatus?.in_flight;
  const progress = scrapeStatus?.progress;

  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">

      {/* ── Modals ─────────────────────────────────────────────────────── */}
      {coverModalJob && (
        <CoverLetterModal
          job={coverModalJob}
          candidateId={activeCandidateId}
          onClose={() => setCoverModalJob(null)}
          onSent={() => { setCoverModalJob(null); fetchJobs(); }}
        />
      )}
      {bulkModalJobs && (
        <BulkSendModal
          jobs={bulkModalJobs}
          candidateId={activeCandidateId}
          onClose={() => setBulkModalJobs(null)}
          onQueued={handleBulkSendQueued}
        />
      )}

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Building2 size={20} className="text-blue-600 dark:text-blue-400" />
            Consulting Jobs
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Software engineer roles scraped directly from top consulting & IT outsourcing firms (TCS, Infosys, Deloitte, Toptal, EPAM, ThoughtWorks, etc.)
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Candidate selector */}
          {candidates.length > 0 && (
            <select
              value={activeCandidateId}
              onChange={e => handleCandidateChange(e.target.value)}
              className="text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
            >
              {candidates.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          )}

          {/* Trigger scrape button */}
          <button
            onClick={handleTriggerScrape}
            disabled={scrapeLoading || isScraping}
            title={isScraping ? 'A scrape is already running' : 'Trigger a fresh Consulting scrape'}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {(scrapeLoading || isScraping) ? <Loader2 size={14} className="animate-spin" /> : <Building2 size={14} />}
            {isScraping
              ? (progress ? `Scraping… ${progress.done}/${progress.total}` : 'Scraping…')
              : 'Scrape Consulting Jobs'}
          </button>

          {/* Progress chip */}
          {isScraping && progress && (
            <span className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs border border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300">
              {progress.saved} saved · {progress.done}/{progress.total} companies
            </span>
          )}

          {/* Auto-refresh toggle */}
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

      {/* ── Filters panel ──────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            placeholder="Search company, job title, HR email…"
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
            value={filters.has_hr_email}
            onChange={e => setFilters(f => ({ ...f, has_hr_email: e.target.value as JobFilters['has_hr_email'], page: 1 }))}
            className="text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
          >
            <option value="">Any HR Email</option>
            <option value="yes">Has HR Email</option>
            <option value="no">No HR Email</option>
          </select>
          <select
            value={filters.has_cover}
            onChange={e => setFilters(f => ({ ...f, has_cover: e.target.value as JobFilters['has_cover'], page: 1 }))}
            className="text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
          >
            <option value="">Any Cover</option>
            <option value="yes">Has Cover</option>
            <option value="no">No Cover</option>
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
          </select>

          {/* Min score slider */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">Score ≥ {filters.min_score}%</span>
            <input
              type="range" min={0} max={100} step={5}
              value={filters.min_score}
              onChange={e => setFilters(f => ({ ...f, min_score: Number(e.target.value), page: 1 }))}
              className="w-24 accent-blue-600"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
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

      {/* ── Bulk action toolbar ─────────────────────────────────────────── */}
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
            onClick={handleBulkSend}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700"
          >
            <Send size={12} />
            Send HR ({effectiveCount})
          </button>
          <button
            onClick={handleBulkIgnore}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 text-xs font-medium hover:bg-gray-200 dark:hover:bg-gray-700"
          >
            <Ban size={12} />
            Ignore ({effectiveCount})
          </button>
          <button
            onClick={clearSelection}
            className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
          >
            <X size={12} /> Clear
          </button>
        </div>
      )}

      {/* ── Jobs table ──────────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <Loader2 className="animate-spin text-blue-600" size={24} />
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-12 space-y-3">
            <Building2 size={32} className="mx-auto text-gray-300 dark:text-gray-600" />
            <p className="text-gray-400 dark:text-gray-500">
              No Consulting jobs yet. Click <strong>Scrape Consulting Jobs</strong> to start.
            </p>
          </div>
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
                <SortTh col="company"    label="Company"      sort_by={filters.sort_by} sort_dir={filters.sort_dir} onSort={handleSort} />
                <SortTh col="job_title"  label="Job Title"    sort_by={filters.sort_by} sort_dir={filters.sort_dir} onSort={handleSort} />
                <th className="px-4 py-3 font-medium">Career Page</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <SortTh col="relevance_score" label="Score"   sort_by={filters.sort_by} sort_dir={filters.sort_dir} onSort={handleSort} />
                <th className="px-4 py-3 font-medium w-14" title="Cover letter">Cover</th>
                <th className="px-4 py-3 font-medium w-20">HR Email</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
              {jobs.map(job => {
                const isSelected = selected.has(job.id);
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

                    {/* Company */}
                    <td className="px-4 py-3 max-w-[140px]">
                      <span className="text-gray-700 dark:text-gray-300 font-medium truncate block">
                        {job.company}
                      </span>
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

                    {/* Career Page link */}
                    <td className="px-4 py-3 max-w-[160px]">
                      {job.company_website ? (
                        <a
                          href={job.company_website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 text-blue-500 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 text-xs truncate"
                          title={job.company_website}
                        >
                          <ExternalLink size={11} className="shrink-0" />
                          <span className="truncate">Careers</span>
                        </a>
                      ) : (
                        <span className="text-gray-400 dark:text-gray-500 text-xs">—</span>
                      )}
                    </td>

                    {/* Status */}
                    <td className="px-4 py-3"><StatusBadge status={job.status} /></td>

                    {/* Score */}
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400 font-mono text-xs">
                      {job.relevance_score != null ? `${(job.relevance_score * 100).toFixed(0)}%` : '—'}
                    </td>

                    {/* Cover indicator */}
                    <td className="px-4 py-3 text-center">
                      {job.cover_letter ? (
                        <span title="Cover letter ready" className="flex justify-center">
                          <FileText size={14} className="text-blue-500 dark:text-blue-400" />
                        </span>
                      ) : (
                        <span title="Static cover letter will be used on send" className="flex justify-center">
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

                    {/* Actions */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        {/* Send button */}
                        <button
                          onClick={() => handleRowSend(job)}
                          title={!job.hr_email ? 'No HR email — can override in modal' : 'Send application'}
                          className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
                            job.hr_email
                              ? 'bg-blue-600 text-white hover:bg-blue-700'
                              : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                          }`}
                        >
                          <Send size={11} />
                          Send
                        </button>

                        {/* External job link */}
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

      {/* ── Count + Pagination ───────────────────────────────────────────── */}
      <div className="flex items-center justify-between text-sm text-gray-500 dark:text-gray-400">
        <span>{totalCount.toLocaleString()} Consulting job{totalCount !== 1 ? 's' : ''} matching filters</span>
        <div className="flex items-center gap-3">
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

    </div>
  );
}
