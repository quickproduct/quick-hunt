'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  Bot,
  CheckCircle,
  Briefcase,
  Search,
  LayoutDashboard,
  ChevronRight,
  ArrowRight,
} from 'lucide-react';
import { getMyTenant, updateMyTenant, type Tenant } from '../../lib/api';

// ── Step indicator ─────────────────────────────────────────────────────────────

const WIZARD_STEPS = ['Welcome', 'Configure', 'Done'];

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-center justify-center gap-0 mb-10">
      {WIZARD_STEPS.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <div key={label} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5">
              <span
                className={`flex items-center justify-center w-8 h-8 rounded-full text-sm font-semibold transition-all ${
                  done
                    ? 'bg-emerald-500 text-white'
                    : active
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500'
                }`}
              >
                {done ? (
                  <CheckCircle size={16} strokeWidth={2.5} />
                ) : (
                  i + 1
                )}
              </span>
              <span
                className={`text-xs font-medium ${
                  active
                    ? 'text-blue-600 dark:text-blue-400'
                    : done
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-gray-400 dark:text-gray-500'
                }`}
              >
                {label}
              </span>
            </div>
            {i < WIZARD_STEPS.length - 1 && (
              <div
                className={`w-16 h-px mx-2 mb-5 transition-colors ${
                  i < current
                    ? 'bg-emerald-400 dark:bg-emerald-600'
                    : 'bg-gray-200 dark:bg-gray-700'
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Toggle switch ──────────────────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
  disabled = false,
}: {
  checked: boolean;
  onChange: (val: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-950 ${
        disabled
          ? 'cursor-not-allowed opacity-50'
          : 'cursor-pointer'
      } ${checked ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'}`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  );
}

// ── Completion card links ──────────────────────────────────────────────────────

const NEXT_STEPS = [
  {
    label: 'Add a candidate',
    description: 'Set up your profile for job matching',
    href: '/candidates',
    Icon: Briefcase,
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    border: 'border-blue-100 dark:border-blue-800',
  },
  {
    label: 'Search for jobs',
    description: 'Kick off your first automated search',
    href: '/search',
    Icon: Search,
    color: 'text-purple-600 dark:text-purple-400',
    bg: 'bg-purple-50 dark:bg-purple-900/20',
    border: 'border-purple-100 dark:border-purple-800',
  },
  {
    label: 'View your dashboard',
    description: 'See stats, logs and live activity',
    href: '/',
    Icon: LayoutDashboard,
    color: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-50 dark:bg-emerald-900/20',
    border: 'border-emerald-100 dark:border-emerald-800',
  },
];

// ── Main page ─────────────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const router = useRouter();

  const [step, setStep] = useState(0);

  // tenant data
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [tenantLoading, setTenantLoading] = useState(true);

  // step-2 form state
  const [scoreThreshold, setScoreThreshold] = useState(60);
  const [requiresApproval, setRequiresApproval] = useState(true);
  const [autoSend, setAutoSend] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // fetch tenant on mount
  useEffect(() => {
    getMyTenant()
      .then((t) => {
        setTenant(t);
        setScoreThreshold(t.score_threshold ?? 60);
        setRequiresApproval(t.requires_approval ?? true);
        setAutoSend(t.auto_send ?? false);
      })
      .catch(() => {
        // non-fatal — continue with defaults
      })
      .finally(() => setTenantLoading(false));
  }, []);

  async function handleSave() {
    setSaveError(null);
    setSaveLoading(true);
    try {
      await updateMyTenant({
        score_threshold: scoreThreshold,
        requires_approval: requiresApproval,
        auto_send: autoSend,
      });
      setStep(2);
    } catch (err) {
      const axiosErr = err as {
        response?: { data?: { detail?: string | string[] } };
        message?: string;
      };
      const raw = axiosErr?.response?.data?.detail;
      const detail =
        typeof raw === 'string'
          ? raw
          : Array.isArray(raw)
          ? raw.join(' ')
          : axiosErr?.message || 'Failed to save settings. Please try again.';
      setSaveError(detail);
    } finally {
      setSaveLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 px-4 py-12">
      <div className="mx-auto max-w-2xl">
        {/* Step indicator */}
        <StepIndicator current={step} />

        {/* Card container */}
        <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-sm overflow-hidden">

          {/* ── Step 1: Welcome ──────────────────────────────────────────────── */}
          {step === 0 && (
            <div className="p-8 md:p-10 flex flex-col items-center text-center space-y-6">
              <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-100 dark:bg-blue-900/30">
                <Bot size={36} className="text-blue-600 dark:text-blue-400" />
              </div>

              <div className="space-y-2">
                <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                  Welcome to QuickHunt!
                </h1>
                <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md">
                  Let's get your workspace configured for automated PHP/Laravel job applications.
                </p>
              </div>

              {/* Tenant highlight */}
              {!tenantLoading && tenant && (
                <div className="w-full rounded-xl border border-blue-100 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 px-5 py-4">
                  <p className="text-xs font-medium text-blue-600 dark:text-blue-400 uppercase tracking-wider mb-1">
                    Your workspace
                  </p>
                  <p className="text-base font-semibold text-gray-900 dark:text-gray-100">
                    {tenant.name}
                  </p>
                </div>
              )}
              {tenantLoading && (
                <div className="w-full rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 px-5 py-4 animate-pulse">
                  <div className="h-3 w-24 bg-gray-200 dark:bg-gray-700 rounded mb-2" />
                  <div className="h-4 w-40 bg-gray-200 dark:bg-gray-700 rounded" />
                </div>
              )}

              <button
                type="button"
                onClick={() => setStep(1)}
                className="flex items-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 px-6 py-2.5 text-sm font-semibold text-white transition focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
              >
                Get started
                <ArrowRight size={16} />
              </button>
            </div>
          )}

          {/* ── Step 2: Configure ────────────────────────────────────────────── */}
          {step === 1 && (
            <div className="p-8 md:p-10 space-y-8">
              <div>
                <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
                  Set your preferences
                </h2>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  These settings control how the automation behaves for your workspace.
                </p>
              </div>

              {/* Error banner */}
              {saveError && (
                <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3">
                  <p className="text-sm text-red-700 dark:text-red-400">{saveError}</p>
                </div>
              )}

              <div className="space-y-7">
                {/* Relevance score slider */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <label
                      htmlFor="score-slider"
                      className="text-sm font-medium text-gray-700 dark:text-gray-300"
                    >
                      Minimum relevance score
                    </label>
                    <span className="text-sm font-semibold text-blue-600 dark:text-blue-400 tabular-nums">
                      {scoreThreshold}%
                    </span>
                  </div>
                  <input
                    id="score-slider"
                    type="range"
                    min={0}
                    max={100}
                    step={1}
                    value={scoreThreshold}
                    onChange={(e) => setScoreThreshold(Number(e.target.value))}
                    className="w-full h-2 rounded-full appearance-none bg-gray-200 dark:bg-gray-700 accent-blue-600 cursor-pointer"
                  />
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    Jobs scored below this threshold will be filtered out automatically
                  </p>
                </div>

                <hr className="border-gray-100 dark:border-gray-800" />

                {/* Requires approval toggle */}
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1 min-w-0">
                    <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Require manual approval
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      Recommended: Review applications before they're sent
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      You'll be notified when a new cover letter is ready for review
                    </p>
                  </div>
                  <Toggle
                    checked={requiresApproval}
                    onChange={(val) => {
                      setRequiresApproval(val);
                      // if turning off approval, also turn off autoSend safety lock is gone
                      // if turning ON approval, autoSend must be off
                      if (val) setAutoSend(false);
                    }}
                  />
                </div>

                <hr className="border-gray-100 dark:border-gray-800" />

                {/* Auto-send toggle */}
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className={`text-sm font-medium ${requiresApproval ? 'text-gray-400 dark:text-gray-600' : 'text-gray-700 dark:text-gray-300'}`}>
                        Auto-send applications
                      </p>
                      {requiresApproval && (
                        <span
                          title="Disable manual approval first"
                          className="inline-flex items-center rounded-full bg-amber-100 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-400 cursor-default"
                        >
                          Requires approval is ON
                        </span>
                      )}
                    </div>
                    <p className={`text-xs ${requiresApproval ? 'text-gray-300 dark:text-gray-600' : 'text-gray-400 dark:text-gray-500'}`}>
                      Automatically email approved cover letters to HR contacts
                    </p>
                    {requiresApproval && (
                      <p className="text-xs text-amber-600 dark:text-amber-500">
                        Disable manual approval first to enable auto-send
                      </p>
                    )}
                  </div>
                  <Toggle
                    checked={autoSend}
                    onChange={setAutoSend}
                    disabled={requiresApproval}
                  />
                </div>
              </div>

              <div className="pt-2">
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saveLoading}
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed px-4 py-2.5 text-sm font-semibold text-white transition focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
                >
                  {saveLoading ? (
                    <>
                      <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                        <circle
                          className="opacity-25"
                          cx="12" cy="12" r="10"
                          stroke="currentColor" strokeWidth="4"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                        />
                      </svg>
                      Saving…
                    </>
                  ) : (
                    <>
                      Save & Continue
                      <ArrowRight size={16} />
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* ── Step 3: Done ─────────────────────────────────────────────────── */}
          {step === 2 && (
            <div className="p-8 md:p-10 space-y-8">
              {/* Success hero */}
              <div className="flex flex-col items-center text-center space-y-4">
                <div
                  className="flex items-center justify-center w-20 h-20 rounded-full bg-emerald-100 dark:bg-emerald-900/30"
                  style={{ animation: 'scaleIn 0.4s ease-out both' }}
                >
                  <CheckCircle
                    size={44}
                    className="text-emerald-600 dark:text-emerald-400"
                    strokeWidth={1.75}
                  />
                </div>
                <div className="space-y-1">
                  <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                    You're all set!
                  </h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
                    Your workspace is configured. Here's what happens next:
                  </p>
                </div>
              </div>

              {/* CSS keyframe for scale-in */}
              <style>{`
                @keyframes scaleIn {
                  from { transform: scale(0.6); opacity: 0; }
                  to   { transform: scale(1);   opacity: 1; }
                }
              `}</style>

              {/* Next step cards */}
              <div className="space-y-3">
                {NEXT_STEPS.map(({ label, description, href, Icon, color, bg, border }) => (
                  <button
                    key={href}
                    type="button"
                    onClick={() => router.push(href)}
                    className={`w-full flex items-center gap-4 rounded-xl border ${border} ${bg} px-5 py-4 text-left transition hover:opacity-80 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900`}
                  >
                    <span className={`shrink-0 ${color}`}>
                      <Icon size={22} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        {label}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        {description}
                      </p>
                    </div>
                    <ChevronRight size={16} className="text-gray-400 dark:text-gray-500 shrink-0" />
                  </button>
                ))}
              </div>

              {/* Primary CTA */}
              <button
                type="button"
                onClick={() => router.push('/dashboard')}
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white transition focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-900"
              >
                Go to Dashboard
                <ArrowRight size={16} />
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
