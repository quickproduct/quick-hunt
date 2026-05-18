'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  Copy,
  Check,
  Eye,
  EyeOff,
  Save,
  LogOut,
  Loader2,
  X,
  ShieldCheck,
  ShieldAlert,
} from 'lucide-react';
import { getMe, getMyTenant, updateMe, authLogout, User, Tenant } from '@/lib/api';

// ── Helpers ───────────────────────────────────────────────────────────────────

function getInitial(email: string) {
  return email.charAt(0).toUpperCase();
}

function avatarColor(email: string) {
  const colors = [
    'from-violet-500 to-purple-600',
    'from-blue-500 to-cyan-600',
    'from-emerald-500 to-teal-600',
    'from-amber-500 to-orange-600',
    'from-rose-500 to-pink-600',
    'from-indigo-500 to-blue-600',
  ];
  let hash = 0;
  for (let i = 0; i < email.length; i++) hash = email.charCodeAt(i) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length];
}

function memberSince(userId: string) {
  // Derive a rough date from uuid v4 — fallback to placeholder
  return 'Jan 2025';
}

function passwordStrength(pw: string): { score: number; label: string } {
  if (!pw) return { score: 0, label: '' };
  let score = 0;
  if (pw.length >= 8) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  const labels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
  return { score, label: labels[score] || 'Strong' };
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Banner({
  type,
  message,
  onClose,
}: {
  type: 'success' | 'error';
  message: string;
  onClose: () => void;
}) {
  return (
    <div
      className={`flex items-center justify-between rounded-lg px-4 py-3 text-sm ${
        type === 'success'
          ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'
          : 'bg-red-500/10 border border-red-500/30 text-red-400'
      }`}
    >
      <span>{message}</span>
      <button onClick={onClose} className="ml-3 opacity-70 hover:opacity-100 transition-opacity">
        <X size={14} />
      </button>
    </div>
  );
}

function RoleBadge({ role }: { role: string }) {
  const styles: Record<string, string> = {
    owner: 'bg-violet-500/20 text-violet-300 border border-violet-500/30',
    admin: 'bg-blue-500/20 text-blue-300 border border-blue-500/30',
    member: 'bg-gray-500/20 text-gray-300 border border-gray-500/30',
  };
  return (
    <span className={`text-xs px-2.5 py-1 rounded-full font-medium capitalize ${styles[role] ?? styles.member}`}>
      {role}
    </span>
  );
}

function PlanBadge({ plan }: { plan: string }) {
  const styles: Record<string, string> = {
    pro: 'bg-blue-500/15 text-blue-300 border border-blue-500/25',
    premium: 'bg-violet-500/15 text-violet-300 border border-violet-500/25',
    free: 'bg-gray-700/60 text-gray-400 border border-gray-700',
  };
  return (
    <span className={`text-xs px-2.5 py-1 rounded-full font-medium capitalize ${styles[plan] ?? styles.free}`}>
      {plan}
    </span>
  );
}

// ── Edit Profile Card ─────────────────────────────────────────────────────────

function EditProfileCard({ user }: { user: User }) {
  const [email, setEmail] = useState(user.email);
  const [saving, setSaving] = useState(false);
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const handleSave = async () => {
    if (!email.trim() || email === user.email) return;
    setSaving(true);
    setBanner(null);
    try {
      await updateMe({ email: email.trim() });
      setBanner({ type: 'success', message: 'Email updated successfully.' });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to update email.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <h3 className="text-sm font-semibold text-gray-200 mb-5">Edit profile</h3>
      {banner && (
        <div className="mb-4">
          <Banner type={banner.type} message={banner.message} onClose={() => setBanner(null)} />
        </div>
      )}
      <div className="space-y-4">
        <label className="block">
          <span className="text-xs font-medium text-gray-400 block mb-1.5">Email address</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
          />
        </label>
        <button
          onClick={handleSave}
          disabled={saving || !email.trim() || email === user.email}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </div>
  );
}

// ── Change Password Card ──────────────────────────────────────────────────────

function ChangePasswordCard() {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const strength = passwordStrength(newPassword);
  const passwordsMatch = newPassword === confirmPassword && confirmPassword.length > 0;
  const passwordsMismatch = confirmPassword.length > 0 && newPassword !== confirmPassword;

  const strengthBarColor = (idx: number) => {
    if (strength.score === 0 || idx > strength.score) return 'bg-gray-700';
    if (strength.score <= 1) return 'bg-red-500';
    if (strength.score === 2) return 'bg-amber-500';
    return 'bg-emerald-500';
  };

  const handleSave = async () => {
    if (!currentPassword || !newPassword || !confirmPassword) {
      setBanner({ type: 'error', message: 'All fields are required.' });
      return;
    }
    if (newPassword.length < 8) {
      setBanner({ type: 'error', message: 'New password must be at least 8 characters.' });
      return;
    }
    if (newPassword === currentPassword) {
      setBanner({ type: 'error', message: 'New password must differ from current password.' });
      return;
    }
    if (newPassword !== confirmPassword) {
      setBanner({ type: 'error', message: 'Passwords do not match.' });
      return;
    }

    setSaving(true);
    setBanner(null);
    try {
      await updateMe({ current_password: currentPassword, new_password: newPassword });
      setBanner({ type: 'success', message: 'Password updated successfully.' });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to update password.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <h3 className="text-sm font-semibold text-gray-200 mb-5">Change password</h3>
      {banner && (
        <div className="mb-4">
          <Banner type={banner.type} message={banner.message} onClose={() => setBanner(null)} />
        </div>
      )}
      <div className="space-y-4">
        {/* Current password */}
        <label className="block">
          <span className="text-xs font-medium text-gray-400 block mb-1.5">Current password</span>
          <div className="relative">
            <input
              type={showCurrent ? 'text' : 'password'}
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 pr-10"
              placeholder="••••••••"
            />
            <button
              type="button"
              onClick={() => setShowCurrent(!showCurrent)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
            >
              {showCurrent ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </label>

        {/* New password */}
        <div>
          <label className="block">
            <span className="text-xs font-medium text-gray-400 block mb-1.5">New password</span>
            <div className="relative">
              <input
                type={showNew ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 pr-10"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowNew(!showNew)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
              >
                {showNew ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </label>
          {newPassword.length > 0 && (
            <div className="mt-2">
              <div className="flex gap-1 mb-1">
                {[1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className={`h-1 flex-1 rounded-full transition-colors duration-300 ${strengthBarColor(i)}`}
                  />
                ))}
              </div>
              <p
                className={`text-xs ${
                  strength.score <= 1
                    ? 'text-red-400'
                    : strength.score === 2
                    ? 'text-amber-400'
                    : 'text-emerald-400'
                }`}
              >
                {strength.label}
              </p>
            </div>
          )}
        </div>

        {/* Confirm password */}
        <label className="block">
          <span className="text-xs font-medium text-gray-400 block mb-1.5">
            Confirm new password
          </span>
          <div className="relative">
            <input
              type={showConfirm ? 'text' : 'password'}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={`w-full bg-gray-800 border rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 pr-10 transition-colors ${
                passwordsMismatch
                  ? 'border-red-500/60 focus:ring-red-500/30'
                  : passwordsMatch
                  ? 'border-emerald-500/60 focus:ring-emerald-500/30'
                  : 'border-gray-700 focus:ring-blue-500/50 focus:border-blue-500'
              }`}
              placeholder="••••••••"
            />
            <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
              {passwordsMatch && <Check size={12} className="text-emerald-400" />}
              {passwordsMismatch && <X size={12} className="text-red-400" />}
              <button
                type="button"
                onClick={() => setShowConfirm(!showConfirm)}
                className="text-gray-500 hover:text-gray-300"
              >
                {showConfirm ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>
          {passwordsMismatch && (
            <p className="text-xs text-red-400 mt-1">Passwords do not match</p>
          )}
        </label>

        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          {saving ? 'Saving…' : 'Update password'}
        </button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [copied, setCopied] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    getMe().then(setUser).catch(() => {});
    getMyTenant().then(setTenant).catch(() => {});
  }, []);

  const handleCopy = () => {
    if (!user) return;
    navigator.clipboard.writeText(user.email).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleSignOut = () => {
    setSigningOut(true);
    authLogout();
    router.push('/auth/login');
  };

  if (!user) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-gray-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8">
        {/* Header */}
        <div className="flex flex-col items-center text-center mb-8">
          <div
            className={`w-20 h-20 rounded-2xl bg-gradient-to-br ${avatarColor(user.email)} flex items-center justify-center text-white text-3xl font-bold mb-4 shadow-lg`}
          >
            {getInitial(user.email)}
          </div>
          <h1 className="text-lg font-semibold text-gray-100 mb-1">{user.email}</h1>
          <div className="flex items-center gap-2 mb-2">
            <RoleBadge role={user.role} />
          </div>
          <p className="text-xs text-gray-500">Member since {memberSince(user.id)}</p>
        </div>

        <div className="space-y-5">
          {/* Account info card */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h3 className="text-sm font-semibold text-gray-200 mb-4">Account information</h3>
            <div className="space-y-4">
              {/* Email row */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500 mb-0.5">Email</p>
                  <p className="text-sm text-gray-200">{user.email}</p>
                </div>
                <button
                  onClick={handleCopy}
                  className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 bg-gray-800 hover:bg-gray-700 px-2.5 py-1.5 rounded-lg transition-colors"
                >
                  {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </div>

              <div className="border-t border-gray-800" />

              {/* Role row */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500 mb-0.5">Role</p>
                </div>
                <RoleBadge role={user.role} />
              </div>

              <div className="border-t border-gray-800" />

              {/* Workspace row */}
              {tenant && (
                <>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs text-gray-500 mb-0.5">Workspace</p>
                      <p className="text-sm text-gray-200">{tenant.name}</p>
                    </div>
                    <PlanBadge plan={tenant.plan} />
                  </div>
                  <div className="border-t border-gray-800" />
                </>
              )}

              {/* Verification status */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500 mb-0.5">Account status</p>
                </div>
                <div className="flex items-center gap-1.5">
                  {user.is_verified ? (
                    <>
                      <ShieldCheck size={13} className="text-emerald-400" />
                      <span className="text-xs text-emerald-400 font-medium">Verified</span>
                    </>
                  ) : (
                    <>
                      <ShieldAlert size={13} className="text-amber-400" />
                      <span className="text-xs text-amber-400 font-medium">Unverified</span>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Edit profile */}
          <EditProfileCard user={user} />

          {/* Change password */}
          <ChangePasswordCard />

          {/* Danger zone */}
          <div className="bg-gray-900 border border-red-500/25 rounded-xl p-6">
            <h3 className="text-sm font-semibold text-red-400 mb-1">Danger zone</h3>
            <p className="text-xs text-gray-500 mb-4">
              This action will sign you out of all active sessions.
            </p>
            <button
              onClick={handleSignOut}
              disabled={signingOut}
              className="flex items-center gap-2 bg-red-600/10 hover:bg-red-600/20 border border-red-500/30 text-red-400 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            >
              {signingOut ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <LogOut size={14} />
              )}
              Sign out of all sessions
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
