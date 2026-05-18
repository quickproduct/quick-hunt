'use client';

import { useState, useEffect } from 'react';
import { ShieldOff, Plus, Trash2, Pencil, Check, X, Loader2 } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getBlacklist,
  addToBlacklist,
  updateBlacklistEntry,
  removeFromBlacklist,
  type BlacklistedCompany,
} from '@/lib/api';

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-12 h-12 rounded-full bg-gray-800 flex items-center justify-center mb-4">
        <ShieldOff size={22} className="text-gray-500" />
      </div>
      <h3 className="text-sm font-semibold text-gray-200 mb-1">No blacklisted companies</h3>
      <p className="text-xs text-gray-500 mb-5 max-w-xs">
        Companies on this list will never be scraped or emailed.
      </p>
      <button
        onClick={onAdd}
        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
      >
        <Plus size={14} />
        Add company
      </button>
    </div>
  );
}

// ── Skeleton loader ───────────────────────────────────────────────────────────

function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-px">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3 bg-gray-900/40 rounded">
          <div className="h-4 w-48 bg-gray-800 rounded" />
          <div className="h-4 flex-1 bg-gray-800 rounded" />
          <div className="h-4 w-24 bg-gray-800 rounded" />
          <div className="h-6 w-6 bg-gray-800 rounded" />
          <div className="h-6 w-6 bg-gray-800 rounded" />
        </div>
      ))}
    </div>
  );
}

// ── Add form ──────────────────────────────────────────────────────────────────

function AddForm({
  onAdd,
  onCancel,
  saving,
}: {
  onAdd: (name: string, reason: string) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState('');
  const [reason, setReason] = useState('');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    onAdd(name.trim(), reason.trim());
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-gray-900 border border-gray-700 rounded-xl p-5 mb-4"
    >
      <p className="text-sm font-semibold text-gray-100 mb-4">Add company to blacklist</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Company name <span className="text-red-400">*</span>
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. WebMD"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            autoFocus
            required
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Reason <span className="text-gray-600">(optional)</span>
          </label>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Health content network"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
          />
        </div>
      </div>
      <div className="flex gap-2 mt-4">
        <button
          type="submit"
          disabled={saving || !name.trim()}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          Add
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded-lg text-sm font-medium text-gray-400 hover:text-gray-100 hover:bg-gray-800 transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

// ── Inline reason editor ──────────────────────────────────────────────────────

function ReasonCell({
  entry,
  onSave,
}: {
  entry: BlacklistedCompany;
  onSave: (id: string, reason: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(entry.reason ?? '');
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    await onSave(entry.id, value);
    setSaving(false);
    setEditing(false);
  }

  function handleCancel() {
    setValue(entry.reason ?? '');
    setEditing(false);
  }

  if (!editing) {
    return (
      <div className="flex items-center gap-2 group">
        <span className="text-sm text-gray-400 truncate max-w-xs">
          {entry.reason || <span className="text-gray-600 italic">No reason</span>}
        </span>
        <button
          onClick={() => setEditing(true)}
          className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-gray-300 transition-all"
          title="Edit reason"
        >
          <Pencil size={12} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500/50"
        autoFocus
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSave();
          if (e.key === 'Escape') handleCancel();
        }}
      />
      <button
        onClick={handleSave}
        disabled={saving}
        className="text-emerald-400 hover:text-emerald-300 disabled:opacity-50"
        title="Save"
      >
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
      </button>
      <button
        onClick={handleCancel}
        className="text-gray-500 hover:text-gray-300"
        title="Cancel"
      >
        <X size={14} />
      </button>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function BlacklistPage() {
  const [entries, setEntries] = useState<BlacklistedCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');

  useEffect(() => {
    getBlacklist()
      .then(setEntries)
      .catch(() => toast.error('Failed to load blacklist'))
      .finally(() => setLoading(false));
  }, []);

  async function handleAdd(name: string, reason: string) {
    setSaving(true);
    try {
      const entry = await addToBlacklist({ name, reason: reason || undefined });
      setEntries((prev) =>
        [...prev, entry].sort((a, b) => a.name.localeCompare(b.name))
      );
      setShowForm(false);
      toast.success(`"${entry.name}" added to blacklist`);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to add company';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  async function handleUpdateReason(id: string, reason: string) {
    try {
      const updated = await updateBlacklistEntry(id, { reason: reason || null });
      setEntries((prev) => prev.map((e) => (e.id === id ? updated : e)));
      toast.success('Reason updated');
    } catch {
      toast.error('Failed to update reason');
    }
  }

  async function handleDelete(entry: BlacklistedCompany) {
    if (!confirm(`Remove "${entry.name}" from the blacklist?`)) return;
    try {
      await removeFromBlacklist(entry.id);
      setEntries((prev) => prev.filter((e) => e.id !== entry.id));
      toast.success(`"${entry.name}" removed`);
    } catch {
      toast.error('Failed to remove company');
    }
  }

  const filtered = entries.filter((e) =>
    e.name.toLowerCase().includes(search.toLowerCase()) ||
    (e.reason ?? '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Blacklisted Companies</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Jobs from these companies are never scraped or emailed.
          </p>
        </div>
        {!showForm && entries.length > 0 && (
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={14} />
            Add company
          </button>
        )}
      </div>

      {/* Add form */}
      {showForm && (
        <AddForm
          onAdd={handleAdd}
          onCancel={() => setShowForm(false)}
          saving={saving}
        />
      )}

      {/* Search */}
      {entries.length > 5 && (
        <div className="mb-4">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search companies…"
            className="w-full sm:w-72 bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
          />
        </div>
      )}

      {/* Content */}
      {loading ? (
        <TableSkeleton />
      ) : entries.length === 0 ? (
        <EmptyState onAdd={() => setShowForm(true)} />
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[1fr_2fr_auto_auto] gap-4 px-4 py-2.5 bg-gray-800/60 border-b border-gray-800">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Company</span>
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Reason</span>
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Added</span>
            <span className="w-7" />
          </div>

          {/* Rows */}
          {filtered.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-gray-600">
              No results for &ldquo;{search}&rdquo;
            </div>
          ) : (
            filtered.map((entry, idx) => (
              <div
                key={entry.id}
                className={`grid grid-cols-[1fr_2fr_auto_auto] gap-4 items-center px-4 py-3 ${
                  idx < filtered.length - 1 ? 'border-b border-gray-800/60' : ''
                } hover:bg-gray-800/30 transition-colors group`}
              >
                {/* Name */}
                <span className="text-sm font-medium text-gray-200 truncate">{entry.name}</span>

                {/* Reason — inline editable */}
                <ReasonCell entry={entry} onSave={handleUpdateReason} />

                {/* Date */}
                <span className="text-xs text-gray-600 whitespace-nowrap">
                  {new Date(entry.created_at).toLocaleDateString('en-GB', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric',
                  })}
                </span>

                {/* Delete */}
                <button
                  onClick={() => handleDelete(entry)}
                  className="text-gray-700 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                  title={`Remove ${entry.name}`}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))
          )}

          {/* Footer count */}
          <div className="px-4 py-2.5 border-t border-gray-800 bg-gray-800/30">
            <span className="text-xs text-gray-600">
              {filtered.length} {filtered.length === 1 ? 'company' : 'companies'}
              {search && ` matching "${search}"`}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
