'use client';

import { useEffect, useState } from 'react';
import { Send, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { getCandidates, directHRSend, type Candidate } from '../../lib/api';

export default function DirectHRSendPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [candidateId, setCandidateId] = useState('');
  const [hrEmailsRaw, setHrEmailsRaw] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ sent: number; failed: string[]; skipped: string[] } | null>(null);

  useEffect(() => {
    getCandidates()
      .then(setCandidates)
      .catch(() => toast.error('Failed to load candidates'))
      .finally(() => setLoadingCandidates(false));
  }, []);

  const selectedCandidate = candidates.find((c) => c.id === candidateId) ?? null;
  const hasStaticLetter = !!selectedCandidate?.static_cover_letter;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!candidateId) {
      toast.error('Please select a candidate');
      return;
    }
    if (!hrEmailsRaw.trim()) {
      toast.error('Please enter at least one HR email address');
      return;
    }

    const hrEmails = hrEmailsRaw
      .split(/[\n,]+/)
      .map((e) => e.trim())
      .filter(Boolean);

    if (hrEmails.length === 0) {
      toast.error('No valid email addresses found');
      return;
    }

    setSending(true);
    setResult(null);
    try {
      const res = await directHRSend(candidateId, hrEmails);
      setResult(res);
      if (res.sent > 0) {
        toast.success(`Sent to ${res.sent} HR email${res.sent > 1 ? 's' : ''} successfully`);
      }
      if (res.failed.length > 0) {
        toast.error(`${res.failed.length} email${res.failed.length > 1 ? 's' : ''} failed to send`);
      }
      if (res.skipped.length > 0) {
        toast(`${res.skipped.length} already sent — skipped`, { icon: '⊘' });
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to send emails';
      toast.error(msg);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Direct HR Send</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Send your resume and static cover letter directly to a list of HR email addresses —
          no job posting needed.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Candidate picker */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
            Candidate
          </label>
          {loadingCandidates ? (
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <Loader2 size={14} className="animate-spin" /> Loading candidates…
            </div>
          ) : (
            <select
              value={candidateId}
              onChange={(e) => {
                setCandidateId(e.target.value);
                setResult(null);
              }}
              className="w-full border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
            >
              <option value="">— Select a candidate —</option>
              {candidates.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.email})
                </option>
              ))}
            </select>
          )}

          {/* Static cover letter status hint */}
          {candidateId && (
            <p
              className={`mt-1.5 text-xs flex items-center gap-1 ${
                hasStaticLetter ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'
              }`}
            >
              {hasStaticLetter ? (
                <>
                  <CheckCircle2 size={12} /> Static cover letter set — ready to send.
                </>
              ) : (
                <>
                  <AlertCircle size={12} /> No static cover letter. Go to{' '}
                  <a href="/candidates" className="underline">
                    Candidates
                  </a>{' '}
                  and add one first.
                </>
              )}
            </p>
          )}
        </div>

        {/* HR emails input */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
            HR Email Addresses
          </label>
          <textarea
            rows={6}
            value={hrEmailsRaw}
            onChange={(e) => setHrEmailsRaw(e.target.value)}
            placeholder={
              'hr@company1.com, recruiter@company2.com\ntalent@company3.com'
            }
            className="w-full border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-lg px-3 py-2 text-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 resize-y"
          />
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
            Separate addresses with commas or new lines.
          </p>
        </div>

        <button
          type="submit"
          disabled={sending || !candidateId || !hrEmailsRaw.trim() || !hasStaticLetter}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
        >
          {sending ? (
            <Loader2 size={15} className="animate-spin" />
          ) : (
            <Send size={15} />
          )}
          {sending ? 'Sending…' : 'Send Emails'}
        </button>
      </form>

      {/* Result summary */}
      {result && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-3">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Send Results</h2>
          <div className="flex gap-6 text-sm">
            <span className="text-green-600 dark:text-green-400 font-medium">
              ✓ {result.sent} sent
            </span>
            {result.failed.length > 0 && (
              <span className="text-red-500 dark:text-red-400 font-medium">
                ✗ {result.failed.length} failed
              </span>
            )}
            {result.skipped.length > 0 && (
              <span className="text-amber-500 dark:text-amber-400 font-medium">
                ⊘ {result.skipped.length} skipped
              </span>
            )}
          </div>
          {result.failed.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-gray-500 dark:text-gray-400 font-medium">Failed:</p>
              <ul className="space-y-0.5">
                {result.failed.map((f, i) => (
                  <li key={i} className="text-xs text-red-500 dark:text-red-400 font-mono">
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {result.skipped.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-gray-500 dark:text-gray-400 font-medium">Already sent — skipped:</p>
              <ul className="space-y-0.5">
                {result.skipped.map((e, i) => (
                  <li key={i} className="text-xs text-amber-500 dark:text-amber-400 font-mono">
                    {e}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
