'use client';

import { useState, useEffect } from 'react';
import {
  UserPlus,
  Trash2,
  ChevronDown,
  Loader2,
  Users,
  X,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { listUsers, inviteUser, removeUser, changeUserRole, getMe, User } from '@/lib/api';

// ── Helpers ───────────────────────────────────────────────────────────────────

function getInitial(email: string) {
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

function formatJoinDate(id: string) {
  // Stable but illustrative — real apps would use created_at
  return 'Jan 2025';
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
      className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${
        styles[role] ?? styles.member
      }`}
    >
      {role}
    </span>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ onInvite }: { onInvite: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      <div className="w-16 h-16 rounded-2xl bg-gray-800 flex items-center justify-center mb-4">
        <Users size={28} className="text-gray-600" />
      </div>
      <h3 className="text-sm font-semibold text-gray-300 mb-1">No team members yet</h3>
      <p className="text-xs text-gray-500 mb-5">
        Invite your first member to collaborate on this workspace.
      </p>
      <button
        onClick={onInvite}
        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
      >
        <UserPlus size={14} />
        Invite member
      </button>
    </div>
  );
}

// ── Table skeleton ────────────────────────────────────────────────────────────

function TableSkeleton() {
  return (
    <div className="p-6 space-y-4">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="flex items-center gap-4 animate-pulse">
          <div className="w-9 h-9 rounded-full bg-gray-800 flex-shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="h-3 bg-gray-800 rounded w-48" />
            <div className="h-2.5 bg-gray-800 rounded w-28" />
          </div>
          <div className="h-5 bg-gray-800 rounded w-16" />
          <div className="h-5 bg-gray-800 rounded w-16" />
          <div className="h-5 bg-gray-800 rounded w-20" />
        </div>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviting, setInviting] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [roleChanging, setRoleChanging] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [usersData, me] = await Promise.all([listUsers(), getMe()]);
      setUsers(usersData);
      setCurrentUser(me);
    } catch {
      toast.error('Failed to load team members.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleInvite = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      await inviteUser({ email: inviteEmail.trim(), role: inviteRole });
      toast.success(`Invitation sent to ${inviteEmail.trim()}`);
      setInviteEmail('');
      setInviteRole('member');
      setShowInviteForm(false);
      loadData();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to send invite.';
      toast.error(msg);
    } finally {
      setInviting(false);
    }
  };

  const handleRemove = async (userId: string, email: string) => {
    try {
      await removeUser(userId);
      setUsers((prev) => prev.filter((u) => u.id !== userId));
      setConfirmRemove(null);
      toast.success(`${email} has been removed.`);
    } catch {
      toast.error('Failed to remove member.');
    }
  };

  const handleRoleChange = async (userId: string, role: string, email: string) => {
    setRoleChanging(userId);
    try {
      const updated = await changeUserRole(userId, role);
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
      toast.success(`${email} is now ${role}.`);
    } catch {
      toast.error('Failed to change role.');
    } finally {
      setRoleChanging(null);
    }
  };

  const openInviteForm = () => {
    setShowInviteForm(true);
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        {/* Page header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-xl font-semibold text-gray-100">Team</h1>
            <p className="text-sm text-gray-500 mt-1">Manage your workspace members</p>
          </div>
          <button
            onClick={openInviteForm}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <UserPlus size={15} />
            Invite member
          </button>
        </div>

        {/* Collapsible invite form */}
        <div
          className={`overflow-hidden transition-all duration-300 ${
            showInviteForm ? 'max-h-64 opacity-100 mb-5' : 'max-h-0 opacity-0'
          }`}
        >
          <div className="bg-gray-900 border border-blue-500/30 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-sm font-semibold text-gray-200">Invite a new member</h4>
              <button
                onClick={() => {
                  setShowInviteForm(false);
                  setInviteEmail('');
                }}
                className="text-gray-500 hover:text-gray-300 transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex flex-col sm:flex-row gap-3">
              <input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                placeholder="colleague@company.com"
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
                onKeyDown={(e) => e.key === 'Enter' && handleInvite()}
                autoFocus
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
                className="bg-gray-800 hover:bg-gray-700 text-gray-300 px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>

        {/* Users table card */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          {loading ? (
            <TableSkeleton />
          ) : users.length === 0 ? (
            <EmptyState onInvite={openInviteForm} />
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left text-xs font-medium text-gray-500 px-5 py-3">
                    Member
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 px-4 py-3">Role</th>
                  <th className="text-left text-xs font-medium text-gray-500 px-4 py-3">
                    Status
                  </th>
                  <th className="text-left text-xs font-medium text-gray-500 px-4 py-3 hidden sm:table-cell">
                    Joined
                  </th>
                  <th className="text-right text-xs font-medium text-gray-500 px-5 py-3">
                    Actions
                  </th>
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
                      {/* Member */}
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-semibold flex-shrink-0 ${avatarColor(
                              user.email
                            )}`}
                          >
                            {getInitial(user.email)}
                          </div>
                          <div>
                            <p className="text-sm text-gray-200 leading-tight">
                              {user.email}
                              {isCurrentUser && (
                                <span className="ml-1.5 text-xs text-blue-400">(you)</span>
                              )}
                            </p>
                          </div>
                        </div>
                      </td>

                      {/* Role */}
                      <td className="px-4 py-3.5">
                        <RoleBadge role={user.role} />
                      </td>

                      {/* Status */}
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

                      {/* Join date */}
                      <td className="px-4 py-3.5 hidden sm:table-cell">
                        <span className="text-xs text-gray-500">{formatJoinDate(user.id)}</span>
                      </td>

                      {/* Actions */}
                      <td className="px-5 py-3.5">
                        {!isOwner && !isCurrentUser ? (
                          <div className="flex items-center justify-end gap-2">
                            {/* Role change */}
                            <div className="relative">
                              <select
                                value={user.role}
                                disabled={roleChanging === user.id}
                                onChange={(e) =>
                                  handleRoleChange(user.id, e.target.value, user.email)
                                }
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

                            {/* Remove */}
                            {confirmRemove === user.id ? (
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={() => handleRemove(user.id, user.email)}
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
                        ) : (
                          <div className="flex justify-end">
                            {isOwner && (
                              <span className="text-xs text-gray-600 italic pr-1">Owner</span>
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

        {/* Member count */}
        {!loading && users.length > 0 && (
          <p className="text-xs text-gray-600 mt-3 text-right">
            {users.length} member{users.length !== 1 ? 's' : ''} in this workspace
          </p>
        )}
    </div>
  );
}
