'use client';

import { useState } from 'react';
import { X, Send, Save, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { sendApplication, updateJobStatus } from '../lib/api';
import type { Job } from '../lib/api';

interface CoverLetterModalProps {
  job: Job;
  candidateId: string;
  onClose: () => void;
  onSent?: () => void;
}

export default function CoverLetterModal({ job, candidateId, onClose, onSent }: CoverLetterModalProps) {
  const [cover, setCover] = useState(job.cover_letter || '');
  const [sending, setSending] = useState(false);
  const [dryRun, setDryRun] = useState(false);

  const handleSend = async () => {
    setSending(true);
    try {
      const result = await sendApplication(job.id, {
        candidate_id: candidateId,
        dry_run: dryRun,
        attach_resume: true,
        override_subject: undefined,
        override_email: undefined,
      }, cover !== job.cover_letter ? cover : undefined);
      if (dryRun) {
        toast.success('Dry run complete — email NOT sent');
      } else {
        toast.success('Application sent!');
        onSent?.();
        onClose();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to send';
      toast.error(msg);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-2xl mx-4 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-gray-800">
          <div>
            <h2 className="font-bold text-gray-900 dark:text-gray-100">{job.job_title}</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">{job.company}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <X size={18} />
          </button>
        </div>

        {/* Cover letter editor */}
        <div className="flex-1 p-5 overflow-auto">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Cover Letter
          </label>
          <textarea
            value={cover}
            onChange={e => setCover(e.target.value)}
            rows={12}
            className="w-full rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            placeholder="Cover letter will appear here after generation..."
          />
          {job.hr_email && (
            <p className="text-xs text-green-600 dark:text-green-400 mt-2">
              Will be sent to: {job.hr_email}
            </p>
          )}
          {!job.hr_email && (
            <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-2">
              ⚠ No HR email found — discovery needed before sending
            </p>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex items-center gap-3 p-5 border-t border-gray-200 dark:border-gray-800">
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 cursor-pointer">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={e => setDryRun(e.target.checked)}
              className="rounded"
            />
            Dry run (preview only)
          </label>
          <div className="flex-1" />
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Cancel
          </button>
          <button
            onClick={handleSend}
            disabled={sending || !cover || !job.hr_email}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            {dryRun ? 'Preview' : 'Send Application'}
          </button>
        </div>
      </div>
    </div>
  );
}
