'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Bot, Building2, Mail, Lock, Eye, EyeOff, Check } from 'lucide-react';
import { authRegister, getAccessToken } from '../../../lib/api';

// ── Feature bullets ────────────────────────────────────────────────────────────

const FEATURES = [
  'Multi-tenant workspace',
  'Role-based team access',
  'Billing & subscription management',
];

// ── Password strength ──────────────────────────────────────────────────────────

type StrengthLevel = 'weak' | 'medium' | 'strong' | null;

function getStrength(password: string): StrengthLevel {
  if (password.length === 0) return null;
  if (password.length <= 7) return 'weak';
  if (password.length <= 11) return 'medium';
  return 'strong';
}

const STRENGTH_CONFIG: Record<
  Exclude<StrengthLevel, null>,
  { label: string; bars: number; color: string; textColor: string }
> = {
  weak: {
    label: 'Weak',
    bars: 1,
    color: 'bg-red-500',
    textColor: 'text-red-600 dark:text-red-400',
  },
  medium: {
    label: 'Medium',
    bars: 2,
    color: 'bg-yellow-500',
    textColor: 'text-yellow-600 dark:text-yellow-400',
  },
  strong: {
    label: 'Strong',
    bars: 3,
    color: 'bg-green-500',
    textColor: 'text-green-600 dark:text-green-400',
  },
};

function PasswordStrength({ password }: { password: string }) {
  const level = getStrength(password);
  if (!level) return null;
  const config = STRENGTH_CONFIG[level];

  return (
    <div className="mt-2 space-y-1.5">
      <div className="flex gap-1">
        {[1, 2, 3].map((bar) => (
          <div
            key={bar}
            className={`h-1 flex-1 rounded-full transition-colors duration-200 ${
              bar <= config.bars ? config.color : 'bg-gray-200 dark:bg-gray-700'
            }`}
          />
        ))}
      </div>
      <p className={`text-xs font-medium ${config.textColor}`}>
        Password strength: {config.label}
      </p>
    </div>
  );
}

// ── Register page ──────────────────────────────────────────────────────────────

export default function RegisterPage() {
  const router = useRouter();

  const [tenantName, setTenantName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Redirect if already authenticated
  useEffect(() => {
    if (getAccessToken()) {
      router.replace('/');
    }
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await authRegister({
        tenant_name: tenantName.trim(),
        email: email.trim(),
        password,
      });
      router.push('/onboarding');
    } catch (err: unknown) {
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
          : axiosErr?.message || 'Registration failed. Please try again.';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-white dark:bg-gray-950">
      {/* ── Left panel (hidden on mobile) ── */}
      <div className="hidden md:flex md:w-2/5 flex-col justify-between bg-gradient-to-br from-violet-700 to-purple-900 p-10 text-white">
        <div className="flex items-center gap-3">
          <Bot size={28} />
          <span className="text-xl font-bold tracking-tight">QuickHunt</span>
        </div>

        <div className="space-y-8">
          <h1 className="text-3xl font-bold leading-snug">
            Set up your workspace in seconds
          </h1>

          <ul className="space-y-3">
            {FEATURES.map((feat) => (
              <li key={feat} className="flex items-center gap-3">
                <span className="flex items-center justify-center w-5 h-5 rounded-full bg-white/20 shrink-0">
                  <Check size={12} strokeWidth={3} />
                </span>
                <span className="text-white/90 text-sm">{feat}</span>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-white/40 text-xs">
          &copy; {new Date().getFullYear()} QuickHunt. All rights reserved.
        </p>
      </div>

      {/* ── Right panel ── */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 bg-white dark:bg-gray-950">
        <div className="w-full max-w-sm space-y-6">
          {/* Mobile logo */}
          <div className="flex items-center gap-2 md:hidden">
            <Bot size={22} className="text-violet-600 dark:text-violet-400" />
            <span className="font-bold text-gray-900 dark:text-gray-100">QuickHunt</span>
          </div>

          {/* Heading */}
          <div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              Create your account
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Start your free job hunt automation
            </p>
          </div>

          {/* Error banner */}
          {error && (
            <div className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3">
              <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            {/* Organisation name */}
            <div className="space-y-1.5">
              <label
                htmlFor="tenant-name"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Organisation name
              </label>
              <div className="relative">
                <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-gray-400 dark:text-gray-500">
                  <Building2 size={16} />
                </span>
                <input
                  id="tenant-name"
                  type="text"
                  autoComplete="organization"
                  required
                  minLength={2}
                  value={tenantName}
                  onChange={(e) => setTenantName(e.target.value)}
                  placeholder="Acme Recruiting"
                  className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 py-2.5 pl-9 pr-3 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 dark:focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/20 transition"
                />
              </div>
            </div>

            {/* Email */}
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
                  className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 py-2.5 pl-9 pr-3 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 dark:focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/20 transition"
                />
              </div>
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label
                htmlFor="password"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Password
              </label>
              <div className="relative">
                <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-gray-400 dark:text-gray-500">
                  <Lock size={16} />
                </span>
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Min. 8 characters"
                  className="w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 py-2.5 pl-9 pr-10 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:border-violet-500 dark:focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/20 transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute inset-y-0 right-3 flex items-center text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>

              {/* Strength indicator */}
              <PasswordStrength password={password} />
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-violet-600 hover:bg-violet-700 active:bg-violet-800 disabled:opacity-60 disabled:cursor-not-allowed px-4 py-2.5 text-sm font-semibold text-white transition-colors focus:outline-none focus:ring-2 focus:ring-violet-500 focus:ring-offset-2 dark:focus:ring-offset-gray-950"
            >
              {loading && (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              )}
              {loading ? 'Creating account...' : 'Create account'}
            </button>
          </form>

          {/* Sign in link */}
          <p className="text-center text-sm text-gray-500 dark:text-gray-400">
            Already have an account?{' '}
            <Link
              href="/auth/login"
              className="font-medium text-violet-600 dark:text-violet-400 hover:underline"
            >
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
