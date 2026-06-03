'use client';

import { useEffect, useState } from 'react';
import { Search, Plus, X, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { triggerSearch, getSearchTask, getCandidates, type Candidate } from '../../lib/api';

const ROLE_PRESETS: Record<string, string[]> = {
  php: [
    'PHP Senior Backend Engineer',
    'PHP Backend Engineer',
    'Laravel Developer',
    'PHP Software Engineer (Backend)',
    'PHP Developer',
    'PHP Full Stack Engineer',
    'PHP Laravel Developer',
  ],
  python: [
    'Python Senior Backend Engineer',
    'Python Backend Engineer',
    'Django Developer',
    'Python Software Engineer (Backend)',
    'Python Developer',
    'FastAPI Developer',
    'Generative AI Engineer',
    'AI Engineer',
    'LLM Engineer',
    'Python AI/ML Backend Engineer',
  ],
};

const PORTALS: { name: string; label?: string; group: string }[] = [
  // Indian portals
  { name: 'naukri',      group: 'India' },
  { name: 'indeed',      group: 'India' },
  { name: 'shine',       group: 'India' },
  { name: 'internshala', group: 'India' },
  // Remote-only portals
  { name: 'remoteok',       group: 'Remote' },
  { name: 'weworkremotely', group: 'Remote' },
  { name: 'workingnomads',  group: 'Remote' },
  { name: 'jobspresso',     group: 'Remote' },
];

export default function SearchPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [form, setForm] = useState({
    candidateId: '',
    jobPosition: 'php',
    jobTitles: ROLE_PRESETS.php,
    locations: ['India', 'Bangalore', 'Remote', 'Mumbai', 'Hyderabad', 'Pune', 'Chennai', 'Delhi', 'Gurgaon', 'Noida'],
    portals: PORTALS.map(p => p.name),
    maxResults: 200,
    autoCovers: true,
  });
  const [submitting, setSubmitting] = useState(false);
  const [taskId, setTaskId] = useState('');
  const [taskStatus, setTaskStatus] = useState<{ status: string; jobs_found: number; error?: string } | null>(null);

  useEffect(() => {
    getCandidates().then(c => {
      setCandidates(c);
      if (c.length > 0) setForm(f => ({ ...f, candidateId: c[0].id }));
    });
  }, []);

  // Poll task status with exponential backoff:
  // starts at 2 s, doubles each tick up to a 15 s ceiling.
  // Stops automatically once the task reaches a terminal state.
  useEffect(() => {
    if (!taskId) return;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    let interval = 2000;
    const MAX_INTERVAL = 15000;
    const MAX_RETRIES = 10;
    let cancelled = false;
    let retryCount = 0;

    const tick = async () => {
      if (cancelled) return;
      try {
        const t = await getSearchTask(taskId);
        retryCount = 0;
        setTaskStatus({ status: t.status, jobs_found: t.jobs_found, error: t.error || undefined });
        if (t.status === 'completed' || t.status === 'error') return;
      } catch (err: unknown) {
        retryCount++;
        if (retryCount >= MAX_RETRIES) {
          setTaskStatus({ status: 'error', jobs_found: 0, error: 'Polling failed after multiple retries' });
          return;
        }
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 401 || status === 403) {
          setTaskStatus({ status: 'error', jobs_found: 0, error: 'Authentication failed' });
          return;
        }
      }
      interval = Math.min(interval * 2, MAX_INTERVAL);
      if (!cancelled) timeoutId = setTimeout(tick, interval);
    };

    timeoutId = setTimeout(tick, interval);
    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [taskId]);

  const addTag = (field: 'jobTitles' | 'locations') => {
    setForm(f => ({ ...f, [field]: [...f[field], ''] }));
  };

  const updateTag = (field: 'jobTitles' | 'locations', i: number, val: string) => {
    setForm(f => {
      const arr = [...f[field]];
      arr[i] = val;
      return { ...f, [field]: arr };
    });
  };

  const removeTag = (field: 'jobTitles' | 'locations', i: number) => {
    setForm(f => ({ ...f, [field]: f[field].filter((_, idx) => idx !== i) }));
  };

  const togglePortal = (portal: string) => {
    setForm(f => ({
      ...f,
      portals: f.portals.includes(portal)
        ? f.portals.filter(p => p !== portal)
        : [...f.portals, portal],
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const titles = form.jobTitles.filter(Boolean);
    const locs = form.locations.filter(Boolean);
    if (!titles.length) return toast.error('Add at least one job title');
    if (!form.portals.length) return toast.error('Select at least one portal');
    if (!form.candidateId) return toast.error('Select a candidate');

    setSubmitting(true);
    setTaskStatus(null);
    try {
      const result = await triggerSearch({
        job_titles: titles,
        locations: locs,
        portals: form.portals,
        max_results_per_portal: form.maxResults,
        candidate_id: form.candidateId,
        auto_generate_covers: form.autoCovers,
      });
      setTaskId(result.task_id);
      toast.success(result.message);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Failed to start search');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">New Search</h1>

      <form onSubmit={handleSubmit} className="space-y-6 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
        {/* Candidate */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Candidate</label>
          <select
            value={form.candidateId}
            onChange={e => setForm(f => ({ ...f, candidateId: e.target.value }))}
            className="w-full text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2"
          >
            {candidates.map(c => <option key={c.id} value={c.id}>{c.name} ({c.email})</option>)}
          </select>
        </div>

        {/* Job Position */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Job Position</label>
          <select
            value={form.jobPosition}
            onChange={e => setForm(f => ({ ...f, jobPosition: e.target.value, jobTitles: ROLE_PRESETS[e.target.value] }))}
            className="w-full text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2"
          >
            <option value="php">PHP Role</option>
            <option value="python">Python Role</option>
          </select>
        </div>

        {/* Job titles */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Job Titles</label>
          <div className="space-y-2">
            {form.jobTitles.map((t, i) => (
              <div key={i} className="flex gap-2">
                <input
                  value={t}
                  onChange={e => updateTag('jobTitles', i, e.target.value)}
                  placeholder="e.g. Backend Engineer"
                  className="flex-1 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
                />
                {form.jobTitles.length > 1 && (
                  <button type="button" onClick={() => removeTag('jobTitles', i)} className="text-red-400 hover:text-red-600"><X size={16} /></button>
                )}
              </div>
            ))}
            <button type="button" onClick={() => addTag('jobTitles')} className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700">
              <Plus size={14} /> Add title
            </button>
          </div>
        </div>

        {/* Locations */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Locations</label>
          <div className="space-y-2">
            {form.locations.map((l, i) => (
              <div key={i} className="flex gap-2">
                <input
                  value={l}
                  onChange={e => updateTag('locations', i, e.target.value)}
                  placeholder="e.g. Bangalore"
                  className="flex-1 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
                />
                {form.locations.length > 1 && (
                  <button type="button" onClick={() => removeTag('locations', i)} className="text-red-400 hover:text-red-600"><X size={16} /></button>
                )}
              </div>
            ))}
            <button type="button" onClick={() => addTag('locations')} className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700">
              <Plus size={14} /> Add location
            </button>
          </div>
        </div>

        {/* Portals */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Portals</label>
          {(['India', 'Remote'] as const).map(group => (
            <div key={group} className="mb-3">
              <p className="text-xs text-gray-400 dark:text-gray-500 mb-1.5 uppercase tracking-wide">{group}</p>
              <div className="flex flex-wrap gap-2">
                {PORTALS.filter(p => p.group === group).map(p => (
                  <button
                    key={p.name}
                    type="button"
                    onClick={() => togglePortal(p.name)}
                    className={`px-3 py-1 rounded-full text-sm font-medium border transition-colors ${
                      form.portals.includes(p.name)
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-blue-400'
                    }`}
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Max results slider */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Max Results per Portal: <span className="text-blue-600">{form.maxResults}</span>
          </label>
          <input
            type="range"
            min={10}
            max={200}
            step={10}
            value={form.maxResults}
            onChange={e => setForm(f => ({ ...f, maxResults: parseInt(e.target.value) }))}
            className="w-full"
          />
        </div>

        {/* Auto covers */}
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={form.autoCovers}
            onChange={e => setForm(f => ({ ...f, autoCovers: e.target.checked }))}
            className="rounded"
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">Auto-generate cover letters for found jobs</span>
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />}
          Start Search
        </button>
      </form>

      {/* Task progress */}
      {taskStatus && (
        <div className={`flex items-center gap-3 p-4 rounded-xl border ${
          taskStatus.status === 'completed' ? 'border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/20' :
          taskStatus.status === 'error' ? 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/20' :
          'border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-900/20'
        }`}>
          {taskStatus.status === 'completed' ? <CheckCircle size={20} className="text-green-600" /> :
           taskStatus.status === 'error' ? <AlertCircle size={20} className="text-red-600" /> :
           <Loader2 size={20} className="animate-spin text-blue-600" />}
          <div>
            <p className="text-sm font-medium">
              {taskStatus.status === 'completed' ? `Done — ${taskStatus.jobs_found} new jobs found` :
               taskStatus.status === 'error' ? `Error: ${taskStatus.error}` :
               'Search in progress...'}
            </p>
            <p className="text-xs text-gray-500">Task: {taskId}</p>
          </div>
        </div>
      )}
    </div>
  );
}
