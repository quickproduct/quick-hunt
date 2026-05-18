'use client';

import { useState } from 'react';
import { X, Send, Mail, FileText, AlertTriangle, CheckCircle, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { bulkSendApplications } from '../lib/api';
import type { Job, BulkSendResult } from '../lib/api';

interface BulkSendModalProps {
  jobs: Job[];
  candidateId: string;
  onClose: () => void;
  onQueued: (result: BulkSendResult) => void;
}

const SKIP_REASON_LABELS: Record<string, string> = {
  no_hr_email: 'No HR email',
  no_cover_letter: 'No cover letter',
  already_sent: 'Already sent',
  not_found: 'Not found',
};

export default function BulkSendModal({ jobs, candidateId, onClose, onQueued }: BulkSendModalProps) {
  const [dryRun, setDryRun] = useState(false);
  const [attachResume, setAttachResume] = useState(true);
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<BulkSendResult | null>(null);

  const readyJobs   = jobs.filter(j => j.hr_email && j.cover_letter);
  const noEmailJobs = jobs.filter(j => !j.hr_email);
  const noCoverJobs = jobs.filter(j => j.hr_email && !j.cover_letter);

  const handleSend = async () => {
    setSending(true);
    try {
      const r = await bulkSendApplications(
        readyJobs.map(j => j.id),
        candidateId,
        { dry_run: dryRun, attach_resume: attachResume }
      );
      setResult(r);
      onQueued(r);
      if (dryRun) {
        toast.success(`Dry run: ${r.queued} would be sent`);
      } else {
        toast.success(`${r.queued} applications queued!`);
      }
    } catch {
      toast.error('Bulk send failed');
    } finally {
      setSending(false);
    }
  };

  const getJobDotColor = (job: Job) => {
    if (job.hr_email && job.cover_letter) return 'bg-green-500';
    if (!job.hr_email) return 'bg-red-400';
    return 'bg-yellow-400';
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-xl mx-4 flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-gray-800">
          <div>
            <h2 className="font-bold text-gray-900 dark:text-gray-100">
              Send {jobs.length} Application{jobs.length !== 1 ? 's' : ''}
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Review readiness before sending
            </p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">
            <X size={18} />
          </button>
        </div>

        {result ? (
          /* Post-send result view */
          <div className="flex-1 p-5 overflow-auto space-y-4">
            <div className="flex items-center gap-3 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
              <CheckCircle size={20} className="text-green-600 dark:text-green-400 shrink-0" />
              <div>
                <p className="font-medium text-green-800 dark:text-green-300">
                  {result.dry_run ? 'Dry run complete' : `${result.queued} application${result.queued !== 1 ? 's' : ''} queued`}
                </p>
                <p className="text-sm text-green-700 dark:text-green-400">
                  {result.dry_run ? `${result.queued} would be sent` : 'Emails are being sent in the background'}
                </p>
              </div>
            </div>

            {result.skipped.length > 0 && (
              <div>
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Skipped ({result.skipped.length})
                </p>
                <div className="space-y-1.5 max-h-48 overflow-y-auto">
                  {result.skipped.map(s => {
                    const job = jobs.find(j => j.id === s.job_id);
                    return (
                      <div key={s.job_id} className="flex items-center justify-between text-sm px-3 py-2 bg-gray-50 dark:bg-gray-800 rounded-lg">
                        <span className="text-gray-700 dark:text-gray-300 truncate">
                          {job ? `${job.job_title} — ${job.company}` : s.job_id}
                        </span>
                        <span className="ml-3 shrink-0 text-xs text-orange-600 dark:text-orange-400 font-medium">
                          {SKIP_REASON_LABELS[s.reason] ?? s.reason}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Pre-send view */
          <div className="flex-1 overflow-auto">
            {/* Readiness summary */}
            <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100 dark:border-gray-800">
              <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">
                <CheckCircle size={11} /> {readyJobs.length} ready
              </span>
              {noCoverJobs.length > 0 && (
                <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400">
                  <FileText size={11} /> {noCoverJobs.length} missing cover
                </span>
              )}
              {noEmailJobs.length > 0 && (
                <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400">
                  <Mail size={11} /> {noEmailJobs.length} no HR email
                </span>
              )}
            </div>

            {/* Job list */}
            <div className="max-h-64 overflow-y-auto divide-y divide-gray-50 dark:divide-gray-800">
              {jobs.map(job => (
                <div key={job.id} className="flex items-center gap-3 px-5 py-2.5">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${getJobDotColor(job)}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{job.job_title}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{job.company}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    {job.hr_email ? (
                      <p className="text-xs text-gray-400 dark:text-gray-500 truncate max-w-[130px]">{job.hr_email}</p>
                    ) : (
                      <span className="text-xs text-red-500 dark:text-red-400">No HR email</span>
                    )}
                    {!job.cover_letter && (
                      <p className="text-xs text-yellow-600 dark:text-yellow-400">No cover</p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Options */}
            <div className="flex items-center gap-5 px-5 py-3 border-t border-gray-100 dark:border-gray-800">
              <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-pointer">
                <input type="checkbox" checked={attachResume} onChange={e => setAttachResume(e.target.checked)} className="rounded" />
                Attach resume
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-pointer">
                <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} className="rounded" />
                Dry run (preview only)
              </label>
            </div>

            {readyJobs.length === 0 && (
              <div className="flex items-center gap-2 mx-5 mb-3 px-3 py-2 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800 text-sm text-yellow-700 dark:text-yellow-400">
                <AlertTriangle size={14} />
                No jobs are ready to send — all are missing HR email or cover letter.
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center gap-3 p-5 border-t border-gray-200 dark:border-gray-800">
          <div className="flex-1" />
          {result ? (
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
            >
              Done
            </button>
          ) : (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleSend}
                disabled={sending || readyJobs.length === 0}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                {dryRun ? `Preview ${readyJobs.length}` : `Send ${readyJobs.length} ready`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
