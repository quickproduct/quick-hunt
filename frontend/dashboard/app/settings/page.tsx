'use client';

import { useState, useEffect } from 'react';
import {
  Settings,
  Users,
  Shield,
  Save,
  UserPlus,
  Trash2,
  ChevronDown,
  AlertTriangle,
  Eye,
  EyeOff,
  Check,
  X,
  Loader2,
} from 'lucide-react';
import {
  getMe,
  getMyTenant,
  updateMyTenant,
  updateMe,
  listUsers,
  inviteUser,
  removeUser,
  changeUserRole,
  User,
  Tenant,
} from '@/lib/api';

// ── Helpers ───────────────────────────────────────────────────────────────────

function getInitials(email: string) {
  return email.charAt(0).toUpperCase();
}

function avatarColor(email: string) {
  const colors = [
    'bg-violet-500',
    'bg-blue-500',
    'bg-emerald-500',
    'bg-amber-500',
    'bg-rose-500',
    'bg-cyan-500',
    'bg-fuchsia-500',
    'bg-indigo-500',
  ];
  let hash = 0;
  for (let i = 0; i < email.length; i++) hash = email.charCodeAt(i) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length];
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

// ── Banner ────────────────────────────────────────────────────────────────────

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
      className={`flex items-center justify-between rounded-lg px-4 py-3 text-sm mb-4 ${
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

// ── Role badge ────────────────────────────────────────────────────────────────

function RoleBadge({ role }: { role: string }) {
  const styles: Record<string, string> = {
    owner: 'bg-violet-500/20 text-violet-300 border border-violet-500/30',
    admin: 'bg-blue-500/20 text-blue-300 border border-blue-500/30',
    member: 'bg-gray-500/20 text-gray-300 border border-gray-500/30',
  };
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[role] ?? styles.member}`}
    >
      {role}
    </span>
  );
}

// ── Toggle switch ─────────────────────────────────────────────────────────────

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`relative flex-shrink-0 w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500/50 ${
        checked ? 'bg-blue-500' : 'bg-gray-700'
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-sm transition-transform duration-200 ${
          checked ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
  );
}

// ── General Tab ───────────────────────────────────────────────────────────────

function GeneralTab({
  tenant,
  onTenantUpdate,
}: {
  tenant: Tenant | null;
  onTenantUpdate: (t: Tenant) => void;
}) {
  const [name, setName] = useState('');
  const [scoreThreshold, setScoreThreshold] = useState(70);
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [autoSend, setAutoSend] = useState(false);
  const [saving, setSaving] = useState(false);
  const [banner, setBanner] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  useEffect(() => {
    if (tenant) {
      setName(tenant.name);
      setScoreThreshold(tenant.score_threshold);
      setRequiresApproval(tenant.requires_approval);
      setAutoSend(tenant.auto_send);
    }
  }, [tenant]);

  const handleSave = async () => {
    setSaving(true);
    setBanner(null);
    try {
      const updated = await updateMyTenant({
        name,
        score_threshold: scoreThreshold,
        requires_approval: requiresApproval,
        auto_send: autoSend,
      });
      onTenantUpdate(updated);
      setBanner({ type: 'success', message: 'Settings saved successfully.' });
    } catch {
      setBanner({ type: 'error', message: 'Failed to save settings. Please try again.' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {banner && (
        <Banner type={banner.type} message={banner.message} onClose={() => setBanner(null)} />
      )}

      {/* Organisation */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-sm font-semibold text-gray-200 mb-4">Organisation</h3>
        <label className="block">
          <span className="text-xs font-medium text-gray-400 block mb-1.5">Organisation name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-colors"
            placeholder="Acme Corp"
          />
        </label>
      </div>

      {/* Automation */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-sm font-semibold text-gray-200 mb-5">Automation</h3>
        <div className="space-y-6">
          {/* Score slider */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-300">Minimum relevance score</span>
              <span className="text-sm font-semibold text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-md tabular-nums">
                {scoreThreshold}%
              </span>
            </div>
            <p className="text-xs text-gray-500 mb-3">
              Only process jobs scoring above this threshold
            </p>
            <input
              type="range"
              min={0}
              max={100}
              value={scoreThreshold}
              onChange={(e) => setScoreThreshold(Number(e.target.value))}
              className="w-full h-2 rounded-full appearance-none bg-gray-700 accent-blue-500 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-gray-600 mt-1.5">
              <span>0%</span>
              <span>50%</span>
              <span>100%</span>
            </div>
          </div>

          {/* Requires approval */}
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-300">Requires manual approval</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Applications wait in queue until manually approved
              </p>
            </div>
            <Toggle checked={requiresApproval} onChange={setRequiresApproval} />
          </div>

          {/* Auto-send */}
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <p className="text-sm font-medium text-gray-300">Auto-send applications</p>
              <p className="text-xs text-gray-500 mt-0.5">
                Send immediately after cover letter is generated
              </p>
              {autoSend && (
                <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-md px-2.5 py-1.5 w-fit">
                  <AlertTriangle size={12} />
                  <span>Only enable if you trust all scraped HR emails</span>
                </div>
              )}
            </div>
            <Toggle checked={autoSend} onChange={setAutoSend} />
          </div>
        </div>
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
      >
        {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
        {saving ? 'Saving…' : 'Save changes'}
      </button>
    </div>
  );
}

// ── Team Tab ──────────────────────────────────────────────────────────────────

function TeamTab({ currentUser }: { currentUser: User | null }) {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviting, setInviting] = useState(false);
  const [inviteBanner, setInviteBanner] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [roleChanging, setRoleChanging] = useState<string | null>(null);

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await listUsers();
      setUsers(data);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    setInviteBanner(null);
    try {
      await inviteUser({ email: inviteEmail.trim(), role: inviteRole });
      setInviteBanner({
        type: 'success',
        message: `Invitation sent to ${inviteEmail.trim()}`,
      });
      setInviteEmail('');
      setInviteRole('member');
      setShowInviteForm(false);
      loadUsers();
    } catch {
      setInviteBanner({ type: 'error', message: 'Failed to send invite. Please try again.' });
    } finally {
      setInviting(false);
    }
  };

  const handleRemove = async (userId: string) => {
    try {
      await removeUser(userId);
      setUsers((prev) => prev.filter((u) => u.id !== userId));
      setConfirmRemove(null);
    } catch {
      // silently fail
    }
  };

  const handleRoleChange = async (userId: string, role: string) => {
    setRoleChanging(userId);
    try {
      const updated = await changeUserRole(userId, role);
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
    } catch {
      // silently fail
    } finally {
      setRoleChanging(null);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-400">Manage your team members and their access levels</p>
        <button
          onClick={() => setShowInviteForm(!showInviteForm)}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <UserPlus size={15} />
          Invite member
        </button>
      </div>

      {inviteBanner && (
        <Banner
          type={inviteBanner.type}
          message={inviteBanner.message}
          onClose={() => setInviteBanner(null)}
        />
      )}

      {/* Inline invite form — slides in */}
      <div
        className={`overflow-hidden transition-all duration-300 ${
          showInviteForm ? 'max-h-56 opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="bg-gray-900 border border-blue-500/30 rounded-xl p-5">
          <h4 className="text-sm font-semibold text-gray-200 mb-4">Invite a new member</h4>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="colleague@company.com"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
              onKeyDown={(e) => e.key === 'Enter' && handleInvite()}
            />
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
            >
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
            <button
              onClick={handleInvite}
              disabled={inviting || !inviteEmail.trim()}
              className="flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
            >
              {inviting && <Loader2 size={14} className="animate-spin" />}
              Send invite
            </button>
            <button
              onClick={() => {
                setShowInviteForm(false);
                setInviteEmail('');
              }}
              className="flex items-center gap-2 bg-gray-800 hover:bg-gray-700 text-gray-300 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>

      {/* Users table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-6 space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-3 animate-pulse">
                <div className="w-8 h-8 rounded-full bg-gray-800" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 bg-gray-800 rounded w-48" />
                </div>
                <div className="h-5 bg-gray-800 rounded w-16" />
                <div className="h-5 bg-gray-800 rounded w-16" />
              </div>
            ))}
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left text-xs font-medium text-gray-500 px-5 py-3">User</th>
                <th className="text-left text-xs font-medium text-gray-500 px-4 py-3">Role</th>
                <th className="text-left text-xs font-medium text-gray-500 px-4 py-3">Status</th>
                <th className="text-right text-xs font-medium text-gray-500 px-5 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {users.map((user) => {
                const isCurrentUser = currentUser?.id === user.id;
                const isOwner = user.role === 'owner';
                return (
                  <tr
                    key={user.id}
                    className={`transition-colors ${
                      isCurrentUser ? 'bg-blue-500/5' : 'hover:bg-gray-800/40'
                    }`}
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div
                          className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold flex-shrink-0 ${avatarColor(user.email)}`}
                        >
                          {getInitials(user.email)}
                        </div>
                        <span className="text-sm text-gray-200">
                          {user.email}
                          {isCurrentUser && (
                            <span className="ml-1.5 text-xs text-blue-400">(you)</span>
                          )}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <RoleBadge role={user.role} />
                    </td>
                    <td className="px-4 py-3.5">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          user.is_active
                            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25'
                            : 'bg-gray-700/50 text-gray-500 border border-gray-700'
                        }`}
                      >
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      {!isOwner && !isCurrentUser && (
                        <div className="flex items-center justify-end gap-2">
                          <div className="relative">
                            <select
                              value={user.role}
                              disabled={roleChanging === user.id}
                              onChange={(e) => handleRoleChange(user.id, e.target.value)}
                              className="appearance-none bg-gray-800 border border-gray-700 rounded-md pl-2.5 pr-7 py-1 text-xs text-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 cursor-pointer"
                            >
                              <option value="member">Member</option>
                              <option value="admin">Admin</option>
                            </select>
                            {roleChanging === user.id ? (
                              <Loader2
                                size={10}
                                className="absolute right-1.5 top-1/2 -translate-y-1/2 animate-spin text-gray-400"
                              />
                            ) : (
                              <ChevronDown
                                size={10}
                                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
                              />
                            )}
                          </div>
                          {confirmRemove === user.id ? (
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => handleRemove(user.id)}
                                className="text-xs bg-red-600 hover:bg-red-500 text-white px-2 py-1 rounded-md transition-colors"
                              >
                                Confirm
                              </button>
                              <button
                                onClick={() => setConfirmRemove(null)}
                                className="text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 px-2 py-1 rounded-md transition-colors"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => setConfirmRemove(user.id)}
                              className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-500/10 rounded-md transition-colors"
                              title="Remove member"
                            >
                              <Trash2 size={13} />
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ── Security Tab ──────────────────────────────────────────────────────────────

function SecurityTab() {
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
      setBanner({
        type: 'error',
        message: 'New password must be different from current password.',
      });
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
    <div className="space-y-6 max-w-lg">
      {banner && (
        <Banner type={banner.type} message={banner.message} onClose={() => setBanner(null)} />
      )}

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h3 className="text-sm font-semibold text-gray-200 mb-5">Change password</h3>
        <div className="space-y-4">
          {/* Current password */}
          <label className="block">
            <span className="text-xs font-medium text-gray-400 block mb-1.5">
              Current password
            </span>
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
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors mt-2"
          >
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
            {saving ? 'Saving…' : 'Update password'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<'general' | 'team' | 'security'>('general');
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [tenant, setTenant] = useState<Tenant | null>(null);

  useEffect(() => {
    getMe().then(setCurrentUser).catch(() => {});
    getMyTenant().then(setTenant).catch(() => {});
  }, []);

  const planBadgeStyle = (plan: string) => {
    if (plan === 'pro') return 'bg-blue-500/15 text-blue-300 border border-blue-500/25';
    if (plan === 'premium') return 'bg-violet-500/15 text-violet-300 border border-violet-500/25';
    return 'bg-gray-700/60 text-gray-400 border border-gray-700';
  };

  const planLabel = (plan: string) => {
    if (plan === 'pro') return 'Pro plan';
    if (plan === 'premium') return 'Premium plan';
    return 'Free plan';
  };

  const tabs = [
    { id: 'general' as const, label: 'General', icon: Settings },
    { id: 'team' as const, label: 'Team', icon: Users },
    { id: 'security' as const, label: 'Security', icon: Shield },
  ];

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        {/* Page header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-xl font-semibold text-gray-100">Settings</h1>
            <p className="text-sm text-gray-500 mt-1">
              Manage your workspace preferences and configuration
            </p>
          </div>
          {tenant && (
            <span
              className={`text-xs px-2.5 py-1 rounded-full font-medium ${planBadgeStyle(
                tenant.plan
              )}`}
            >
              {planLabel(tenant.plan)}
            </span>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 mb-6 w-fit">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === id
                  ? 'bg-gray-800 text-gray-100 shadow-sm'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/40'
              }`}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {activeTab === 'general' && (
          <GeneralTab tenant={tenant} onTenantUpdate={setTenant} />
        )}
        {activeTab === 'team' && <TeamTab currentUser={currentUser} />}
        {activeTab === 'security' && <SecurityTab />}
      </div>
    </div>
  );
}
