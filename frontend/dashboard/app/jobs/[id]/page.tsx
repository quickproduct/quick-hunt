'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, ExternalLink, Mail, Sparkles, Send, Ban, Check, Clock } from 'lucide-react';
import { formatDistanceToNow, format } from 'date-fns';
import toast from 'react-hot-toast';
import StatusBadge from '../../../components/StatusBadge';
import { getJob, generateCoverLetter, updateJobStatus, getCandidates, getJobTimeline, type Job, type Candidate, type TimelineEvent } from '../../../lib/api';
import CoverLetterModal from '../../../components/CoverLetterModal';

function ApplicationTimeline({ jobId }: { jobId: string }) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getJobTimeline(jobId)
      .then((t) => setEvents(t.events))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [jobId]);

  if (loading) return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
      <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-4 text-sm">Application Timeline</h2>
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-full bg-gray-100 dark:bg-gray-800 animate-pulse shrink-0" />
            <div className="h-3 bg-gray-100 dark:bg-gray-800 rounded w-32 animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
      <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-4 text-sm">Application Timeline</h2>
      <ol className="relative">
        {events.map((ev, i) => {
          const isLast = i === events.length - 1;
          return (
            <li key={ev.event} className="flex gap-3 pb-4 last:pb-0">
              {/* connector line */}
              <div className="flex flex-col items-center">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10 ${
                  ev.done
                    ? 'bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-400'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-400'
                }`}>
                  {ev.done ? <Check size={14} strokeWidth={2.5} /> : <Clock size={13} />}
                </div>
                {!isLast && (
                  <div className={`w-px flex-1 mt-1 ${ev.done ? 'bg-green-200 dark:bg-green-800' : 'bg-gray-200 dark:bg-gray-700'}`} />
                )}
              </div>
              {/* content */}
              <div className="pb-1 pt-0.5 min-w-0">
                <p className={`text-sm font-medium leading-5 ${ev.done ? 'text-gray-900 dark:text-gray-100' : 'text-gray-400 dark:text-gray-600'}`}>
                  {ev.label}
                </p>
                {ev.done && ev.timestamp && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {formatDistanceToNow(new Date(ev.timestamp), { addSuffix: true })}
                    <span className="mx-1 opacity-40">·</span>
                    {format(new Date(ev.timestamp), 'MMM d, HH:mm')}
                  </p>
                )}
                {ev.done && ev.metadata && ev.event === 'scored' && ev.metadata.score != null && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    Score: <span className="font-semibold text-blue-600 dark:text-blue-400">{String(ev.metadata.score)}</span>
                  </p>
                )}
                {ev.done && ev.metadata && ev.event === 'email_sent' && Boolean(ev.metadata.to) && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate max-w-[200px]">
                    To: {String(ev.metadata.to)}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState('');
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    Promise.all([getJob(id), getCandidates()])
      .then(([j, c]) => {
        setJob(j);
        setCandidates(c);
        if (c.length > 0) setSelectedCandidate(c[0].id);
        setLoading(false);
      })
      .catch(() => {
        toast.error('Failed to load job details');
        setLoading(false);
      });
  }, [id]);

  const handleGenerate = async () => {
    if (!selectedCandidate) return toast.error('Select a candidate first');
    setGenerating(true);
    try {
      await generateCoverLetter(id, selectedCandidate);
      toast.success('Cover letter generation queued!');
      setTimeout(() => getJob(id).then(setJob), 3000);
    } catch {
      toast.error('Failed to queue generation');
    } finally {
      setGenerating(false);
    }
  };

  const handleIgnore = async () => {
    try {
      await updateJobStatus(id, 'ignored');
      toast.success('Job ignored');
      setJob(j => j ? { ...j, status: 'ignored' } : j);
    } catch {
      toast.error('Failed to ignore job');
    }
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>;
  if (!job) return <div className="text-center py-12 text-gray-400">Job not found</div>;

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Back nav */}
      <Link href="/jobs" className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-900 dark:hover:text-gray-100">
        <ArrowLeft size={16} />
        Back to Jobs
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{job.job_title}</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">{job.company} · {job.location}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <StatusBadge status={job.status} size="md" />
          <StatusBadge status={job.source_portal} size="md" />
        </div>
      </div>

      {/* 4-column layout: metadata | description | cover letter | timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Col 1: metadata */}
        <div className="space-y-4">
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5 space-y-3 text-sm">
            <h2 className="font-semibold text-gray-900 dark:text-gray-100">Details</h2>
            {job.salary_min && <p><span className="text-gray-500">Salary: </span>₹{job.salary_min.toLocaleString()} – ₹{job.salary_max?.toLocaleString()}</p>}
            {job.experience_required && <p><span className="text-gray-500">Experience: </span>{job.experience_required}</p>}
            {job.posted_date && <p><span className="text-gray-500">Posted: </span>{format(new Date(job.posted_date), 'MMM d, yyyy')}</p>}
            {job.scraped_at && <p><span className="text-gray-500">Scraped: </span>{formatDistanceToNow(new Date(job.scraped_at), { addSuffix: true })}</p>}
            {job.hr_email ? (
              <p className="flex items-center gap-1 text-green-600 dark:text-green-400"><Mail size={14} />{job.hr_email}</p>
            ) : (
              <p className="text-yellow-600 dark:text-yellow-400">No HR email found</p>
            )}
            {job.company_website && (
              <a href={job.company_website} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-blue-500 hover:text-blue-600">
                Company site <ExternalLink size={12} />
              </a>
            )}
            <a href={job.job_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-blue-500 hover:text-blue-600">
              Original posting <ExternalLink size={12} />
            </a>
          </div>

          {/* Candidate selector */}
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5 space-y-3">
            <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Apply As</h2>
            <select
              value={selectedCandidate}
              onChange={e => setSelectedCandidate(e.target.value)}
              className="w-full text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5"
            >
              {candidates.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
        </div>

        {/* Col 2: description */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-3 text-sm">Job Description</h2>
          <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap overflow-auto max-h-[480px]">
            {job.job_description || 'No description available'}
          </div>
        </div>

        {/* Col 3: cover letter */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5 flex flex-col">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100 mb-3 text-sm">Cover Letter</h2>
          {job.cover_letter ? (
            <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap flex-1 overflow-auto max-h-[400px]">
              {job.cover_letter}
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
              Not generated yet
            </div>
          )}
          {job.cover_letter_generated_at && (
            <p className="text-xs text-gray-400 mt-2">Generated {formatDistanceToNow(new Date(job.cover_letter_generated_at), { addSuffix: true })}</p>
          )}
        </div>

        {/* Col 4: timeline */}
        <ApplicationTimeline jobId={id} />
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-3 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4">
        <button
          onClick={handleGenerate}
          disabled={generating || !selectedCandidate}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 disabled:opacity-50"
        >
          <Sparkles size={16} />
          {generating ? 'Queued...' : 'Generate Cover Letter'}
        </button>
        {job.cover_letter && job.hr_email && (
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
          >
            <Send size={16} />
            Send Application
          </button>
        )}
        <button
          onClick={handleIgnore}
          className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700 text-sm hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400"
        >
          <Ban size={16} />
          Ignore
        </button>
      </div>

      {showModal && (
        <CoverLetterModal
          job={job}
          candidateId={selectedCandidate}
          onClose={() => setShowModal(false)}
          onSent={() => getJob(id).then(setJob)}
        />
      )}
    </div>
  );
}
