'use client';

import { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Lock,
  Mail,
  ArrowLeft,
  CheckCircle,
  Eye,
  EyeOff,
  AlertCircle,
} from 'lucide-react';
import { forgotPassword, resetPassword } from '../../../lib/api';

// ── Password strength helpers ─────────────────────────────────────────────────

function getStrength(password: string): number {
  let score = 0;
  if (password.length >= 8) score++;
  if (/[A-Z]/.test(password)) score++;
  if (/[0-9]/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;
  return score; // 0–4
}

const STRENGTH_LABELS = ['Weak', 'Fair', 'Good', 'Strong'];
const STRENGTH_COLORS = [
  'bg-red-500',
  'bg-amber-500',
  'bg-amber-400',
  'bg-emerald-500',
];

// ── Left panel decorative steps ───────────────────────────────────────────────

const STEPS = ['Enter email', 'Check inbox', 'Reset password'];

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ForgotPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ForgotPasswordContent />
    </Suspense>
  );
}

function ForgotPasswordContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get('token');

  // ── Forgot-password state ─────────────────────────────────────────────────
  const [email, setEmail] = useState('');
  const [forgotLoading, setForgotLoading] = useState(false);
  const [forgotSuccess, setForgotSuccess] = useState(false);
  const [forgotError, setForgotError] = useState<string | null>(null);

  // ── Reset-password state ──────────────────────────────────────────────────
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const [resetSuccess, setResetSuccess] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  const strength = getStrength(newPassword);
  const passwordsMatch =
    confirmPassword.length > 0 && newPassword === confirmPassword;

  // ── Handlers ──────────────────────────────────────────────────────────────

  function extractDetail(err: unknown, fallback: string): string {
    const axiosErr = err as {
      response?: { data?: { detail?: string | string[] } };
      message?: string;
    };
    const raw = axiosErr?.response?.data?.detail;
    return typeof raw === 'string'
      ? raw
      : Array.isArray(raw)
      ? raw.join(' ')
      : axiosErr?.message || fallback;
  }

  async function handleForgotSubmit(e: React.FormEvent) {
    e.preventDefault();
    setForgotError(null);
    setForgotLoading(true);
    try {
      await forgotPassword(email.trim());
      setForgotSuccess(true);
    } catch (err) {
      setForgotError(
        extractDetail(err, 'Something went wrong. Please try again.')
      );
    } finally {
      setForgotLoading(false);
    }
  }

  async function handleResetSubmit(e: React.FormEvent) {
    e.preventDefault();
    setResetError(null);
    if (newPassword !== confirmPassword) {
      setResetError('Passwords do not match.');
      return;
    }
    if (newPassword.length < 8) {
      setResetError('Password must be at least 8 characters.');
      return;
    }
    setResetLoading(true);
    try {
      await resetPassword(token!, newPassword);
      setResetSuccess(true);
    } catch (err) {
      setResetError(
        extractDetail(err, 'Failed to reset password. The link may have expired.')
      );
    } finally {
      setResetLoading(false);
    }
  }

  async function handleResend() {
    setForgotError(null);
    setForgotSuccess(false);
    setForgotLoading(true);
    try {
      await forgotPassword(email.trim());
      setForgotSuccess(true);
    } catch (err) {
      setForgotError(
        extractDetail(err, 'Something went wrong. Please try again.')
      );
      setForgotSuccess(false);
    } finally {
      setForgotLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex bg-white dark:bg-gray-950">
      {/* ── Left panel ───────────────────────────────────────────────────────── */}
      <div className="hidden md:flex md:w-2/5 flex-col justify-between bg-gradient-to-br from-emerald-700 to-teal-900 p-10 text-white">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <Lock size={22} />
          <span className="text-xl font-bold tracking-tight">QuickHunt</span>
        </div>

        {/* Hero text */}
        <div className="space-y-6">
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-white/15">
            <Lock size={48} className="text-white" strokeWidth={1.5} />
          </div>
          <h1 className="text-3xl font-bold leading-snug">Reset password</h1>
          <p className="text-white/75 text-sm leading-relaxed max-w-xs">
            Enter your email and we'll send you a link to reset your password
          </p>

          {/* Step indicators */}
          <div className="flex items-center gap-0 pt-4">
            {STEPS.map((label, i) => (
              <div key={label} className="flex items-center">
                <div className="flex flex-col items-center gap-1.5">
                  <span className="flex items-center justify-center w-7 h-7 rounded-full bg-white/20 text-white text-xs font-semibold">
                    {i + 1}
                  </span>
                  <span className="text-white/60 text-[10px] whitespace-nowrap">{label}</span>
                </div>
                {i < STEPS.length - 1 && (
                  <div className="w-8 h-px bg-white/30 mb-4 mx-1" />
                )}
              </div>
            ))}
          </div>
        </div>

        <p className="text-white/40 text-xs">
          &copy; {new Date().getFullYear()} QuickHunt. All rights reserved.
        </p>
      </div>

      {/* ── Right panel ──────────────────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 bg-white dark:bg-gray-950">
        <div className="w-full max-w-sm space-y-6">

          {/* Mobile logo */}
          <div className="flex items-center gap-2 md:hidden">
            <Lock size={20} className="text-emerald-600 dark:text-emerald-400" />
            <span className="font-bold text-gray-900 dark:text-gray-100">QuickHunt</span>
          </div>

          {/* ── Forgot flow (no token) ──────────────────────────────────────── */}
          {!token && (
            <>
              {!forgotSuccess ? (
                <>
                  {/* Heading */}
                  <div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                      Forgot password?
                    </h2>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                      No worries, we'll send you reset instructions.
                    </p>
                  </div>

                  {/* Error banner */}
                  {forgotError && (
                    <div className="flex items-start gap-3 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3">
                      <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
                      <p className="text-sm text-red-700 dark:text-red-400">{forgotError}</p>
                    </div>
                  )}

                  {/* Form */}
                  <form onSubmit={handleForgotSubmit} className="space-y-4" noValidate>
                    <div className="space-y-1.5">
                      <label
                        htmlFor="email"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                      >
                        Email address
                      </label>
                      <div className="relative">
                        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-gray-400 dark:text-gray-500">
                          <Mail size={16} />
                        </span>
                        <input
                          id="email"
                          type="email"
                          autoComplete="email"
                          required
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          placeholder="you@example.com"
                          className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 py-2.5 pl-9 pr-3 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-blue-500 dark:focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition"
                        />
                      </div>
                    </div>

                    <button
                      type="submit"
                      disabled={forgotLoading || !email.trim()}
                      className="w-full rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed px-4 py-2.5 text-sm font-semibold text-white transition focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-950"
                    >
                      {forgotLoading ? (
                        <span className="flex items-center justify-center gap-2">
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
                          Sending…
                        </span>
                      ) : (
                        'Send reset link'
                      )}
                    </button>
                  </form>

                  {/* Back to sign in */}
                  <div className="text-center">
                    <Link
                      href="/auth/login"
                      className="inline-flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
                    >
                      <ArrowLeft size={14} />
                      Back to sign in
                    </Link>
                  </div>
                </>
              ) : (
                /* Success card */
                <div className="space-y-6">
                  <div className="rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20 p-6 space-y-3">
                    <div className="flex items-center gap-3">
                      <CheckCircle size={24} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
                      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                        Check your email!
                      </h2>
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
                      We sent a password reset link to{' '}
                      <span className="font-medium text-gray-900 dark:text-gray-100">{email}</span>.
                      The link expires in <span className="font-medium">1 hour</span>.
                    </p>

                    {forgotError && (
                      <div className="flex items-start gap-2 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-3 py-2">
                        <AlertCircle size={14} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
                        <p className="text-xs text-red-700 dark:text-red-400">{forgotError}</p>
                      </div>
                    )}

                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Didn't receive the email?{' '}
                      <button
                        type="button"
                        onClick={handleResend}
                        disabled={forgotLoading}
                        className="font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 disabled:opacity-50 transition-colors"
                      >
                        {forgotLoading ? 'Sending…' : 'Resend email'}
                      </button>
                    </p>
                  </div>

                  <Link
                    href="/auth/login"
                    className="flex items-center justify-center gap-1.5 w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800 px-4 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300 transition"
                  >
                    <ArrowLeft size={14} />
                    Back to sign in
                  </Link>
                </div>
              )}
            </>
          )}

          {/* ── Reset flow (token present) ──────────────────────────────────── */}
          {token && (
            <>
              {!resetSuccess ? (
                <>
                  {/* Heading */}
                  <div>
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                      Set new password
                    </h2>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                      Your new password must be different from previous passwords.
                    </p>
                  </div>

                  {/* Error banner */}
                  {resetError && (
                    <div className="flex items-start gap-3 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3">
                      <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
                      <p className="text-sm text-red-700 dark:text-red-400">{resetError}</p>
                    </div>
                  )}

                  <form onSubmit={handleResetSubmit} className="space-y-5" noValidate>
                    {/* New password */}
                    <div className="space-y-1.5">
                      <label
                        htmlFor="new-password"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                      >
                        New password
                      </label>
                      <div className="relative">
                        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-gray-400 dark:text-gray-500">
                          <Lock size={16} />
                        </span>
                        <input
                          id="new-password"
                          type={showNew ? 'text' : 'password'}
                          autoComplete="new-password"
                          required
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          placeholder="Min. 8 characters"
                          className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 py-2.5 pl-9 pr-10 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-blue-500 dark:focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition"
                        />
                        <button
                          type="button"
                          onClick={() => setShowNew((v) => !v)}
                          aria-label={showNew ? 'Hide password' : 'Show password'}
                          className="absolute inset-y-0 right-3 flex items-center text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                        >
                          {showNew ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>

                      {/* Strength bars */}
                      {newPassword.length > 0 && (
                        <div className="space-y-1">
                          <div className="flex gap-1">
                            {[0, 1, 2, 3].map((i) => (
                              <div
                                key={i}
                                className={`h-1 flex-1 rounded-full transition-colors ${
                                  i < strength
                                    ? STRENGTH_COLORS[strength - 1]
                                    : 'bg-gray-200 dark:bg-gray-700'
                                }`}
                              />
                            ))}
                          </div>
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            Strength:{' '}
                            <span
                              className={
                                strength <= 1
                                  ? 'text-red-600 dark:text-red-400'
                                  : strength === 2
                                  ? 'text-amber-600 dark:text-amber-400'
                                  : 'text-emerald-600 dark:text-emerald-400'
                              }
                            >
                              {STRENGTH_LABELS[strength - 1] ?? 'Very weak'}
                            </span>
                          </p>
                        </div>
                      )}
                    </div>

                    {/* Confirm password */}
                    <div className="space-y-1.5">
                      <label
                        htmlFor="confirm-password"
                        className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                      >
                        Confirm password
                      </label>
                      <div className="relative">
                        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-gray-400 dark:text-gray-500">
                          <Lock size={16} />
                        </span>
                        <input
                          id="confirm-password"
                          type={showConfirm ? 'text' : 'password'}
                          autoComplete="new-password"
                          required
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          placeholder="Repeat your new password"
                          className={`w-full rounded-lg border py-2.5 pl-9 pr-10 text-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 transition bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 ${
                            confirmPassword.length > 0
                              ? passwordsMatch
                                ? 'border-emerald-400 dark:border-emerald-600 focus:border-emerald-500 focus:ring-emerald-500/20'
                                : 'border-red-400 dark:border-red-600 focus:border-red-500 focus:ring-red-500/20'
                              : 'border-gray-200 dark:border-gray-700 focus:border-blue-500 focus:ring-blue-500/20'
                          }`}
                        />
                        <button
                          type="button"
                          onClick={() => setShowConfirm((v) => !v)}
                          aria-label={showConfirm ? 'Hide password' : 'Show password'}
                          className="absolute inset-y-0 right-3 flex items-center text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                        >
                          {showConfirm ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                      {confirmPassword.length > 0 && (
                        <p
                          className={`text-xs ${
                            passwordsMatch
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          {passwordsMatch ? 'Passwords match' : 'Passwords do not match'}
                        </p>
                      )}
                    </div>

                    <button
                      type="submit"
                      disabled={resetLoading || !newPassword || !passwordsMatch}
                      className="w-full rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed px-4 py-2.5 text-sm font-semibold text-white transition focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-950"
                    >
                      {resetLoading ? (
                        <span className="flex items-center justify-center gap-2">
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
                          Resetting…
                        </span>
                      ) : (
                        'Reset password'
                      )}
                    </button>
                  </form>
                </>
              ) : (
                /* Reset success card */
                <div className="space-y-6">
                  <div className="rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/20 p-6 space-y-3">
                    <div className="flex items-center gap-3">
                      <CheckCircle size={24} className="text-emerald-600 dark:text-emerald-400 shrink-0" />
                      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                        Password reset successful!
                      </h2>
                    </div>
                    <p className="text-sm text-gray-600 dark:text-gray-300 leading-relaxed">
                      You can now sign in with your new password.
                    </p>
                  </div>

                  <Link
                    href="/auth/login"
                    className="flex items-center justify-center gap-1.5 w-full rounded-lg bg-blue-600 hover:bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white transition focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 dark:focus:ring-offset-gray-950"
                  >
                    Sign in
                  </Link>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
