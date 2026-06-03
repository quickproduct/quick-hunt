'use client';

import { useEffect, useState } from 'react';
import {
  ListChecks, Plus, Trash2, Pencil, Check, X, Loader2,
  ExternalLink, Globe, User as UserIcon, EyeOff, Eye,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getMncCompanies,
  addMncCompany,
  updateMncCompany,
  removeMncCompany,
  disableMncCompany,
  type MncCompany,
  type MncAts,
} from '../../lib/api';

const ATS_OPTIONS: { value: MncAts; label: string; needsSlug: boolean }[] = [
  { value: 'greenhouse',      label: 'Greenhouse (API)',      needsSlug: true },
  { value: 'lever',           label: 'Lever (API)',           needsSlug: true },
  { value: 'smartrecruiters', label: 'SmartRecruiters (API)', needsSlug: true },
  { value: 'workday',         label: 'Workday (Playwright)',  needsSlug: false },
  { value: 'icims',           label: 'iCIMS (Playwright)',    needsSlug: false },
  { value: 'taleo',           label: 'Taleo (HTML)',          needsSlug: false },
  { value: 'bamboohr',        label: 'BambooHR (Playwright)', needsSlug: false },
  { value: 'custom',          label: 'Custom (Playwright)',   needsSlug: false },
];

function atsNeedsSlug(ats: MncAts): boolean {
  return ATS_OPTIONS.find((o) => o.value === ats)?.needsSlug ?? false;
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-12 h-12 rounded-full bg-gray-800 flex items-center justify-center mb-4">
        <ListChecks size={22} className="text-gray-500" />
      </div>
      <h3 className="text-sm font-semibold text-gray-200 mb-1">No companies in your MNC list</h3>
      <p className="text-xs text-gray-500 mb-5 max-w-xs">
        Only companies in this list are scraped when you click <strong>Scrape MNC Jobs</strong>.
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
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3 bg-gray-900/40 rounded">
          <div className="h-4 w-40 bg-gray-800 rounded" />
          <div className="h-4 flex-1 bg-gray-800 rounded" />
          <div className="h-4 w-24 bg-gray-800 rounded" />
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
  onAdd: (payload: { name: string; career_url: string; ats: MncAts; ats_slug?: string }) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState('');
  const [careerUrl, setCareerUrl] = useState('');
  const [ats, setAts] = useState<MncAts>('custom');
  const [slug, setSlug] = useState('');

  const needsSlug = atsNeedsSlug(ats);
  const slugInvalid = needsSlug && !slug.trim();
  const formValid = name.trim() && careerUrl.trim() && !slugInvalid;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!formValid) return;
    onAdd({
      name: name.trim(),
      career_url: careerUrl.trim(),
      ats,
      ats_slug: needsSlug ? slug.trim() : undefined,
    });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-gray-900 border border-gray-700 rounded-xl p-5 mb-4"
    >
      <p className="text-sm font-semibold text-gray-100 mb-4">Add MNC company</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Company name <span className="text-red-400">*</span>
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Plaid"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            autoFocus
            required
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            Career URL <span className="text-red-400">*</span>
          </label>
          <input
            value={careerUrl}
            onChange={(e) => setCareerUrl(e.target.value)}
            placeholder="https://jobs.lever.co/plaid"
            type="url"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
            required
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">
            ATS / scraping tier <span className="text-red-400">*</span>
          </label>
          <select
            value={ats}
            onChange={(e) => setAts(e.target.value as MncAts)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
          >
            {ATS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        {needsSlug && (
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">
              ATS slug <span className="text-red-400">*</span>
              <span className="text-gray-600 ml-1">(required for {ats})</span>
            </label>
            <input
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="e.g. plaid"
              className={`w-full bg-gray-800 border rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-2 ${
                slugInvalid
                  ? 'border-red-500 focus:ring-red-500/50'
                  : 'border-gray-700 focus:ring-blue-500/50'
              }`}
            />
          </div>
        )}
      </div>
      <div className="flex gap-2 mt-4">
        <button
          type="submit"
          disabled={saving || !formValid}
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

// ── Inline editor for a row ───────────────────────────────────────────────────

function RowEditor({
  entry,
  onSave,
  onCancel,
}: {
  entry: MncCompany;
  onSave: (id: string, patch: Partial<MncCompany>) => Promise<void>;
  onCancel: () => void;
}) {
  const [careerUrl, setCareerUrl] = useState(entry.career_url);
  const [ats, setAts] = useState<MncAts>(entry.ats);
  const [slug, setSlug] = useState(entry.ats_slug ?? '');
  const [saving, setSaving] = useState(false);

  const needsSlug = atsNeedsSlug(ats);
  const slugInvalid = needsSlug && !slug.trim();

  async function handleSave() {
    if (slugInvalid) return;
    setSaving(true);
    await onSave(entry.id, {
      career_url: careerUrl.trim(),
      ats,
      ats_slug: needsSlug ? slug.trim() : null,
    });
    setSaving(false);
  }

  return (
    <div className="grid grid-cols-[1fr_2fr_auto_auto] gap-3 items-center w-full">
      <input
        value={careerUrl}
        onChange={(e) => setCareerUrl(e.target.value)}
        placeholder="career_url"
        className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500/50 col-span-2"
      />
      <select
        value={ats}
        onChange={(e) => setAts(e.target.value as MncAts)}
        className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-500/50"
      >
        {ATS_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.value}</option>
        ))}
      </select>
      {needsSlug && (
        <input
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          placeholder="slug"
          className={`bg-gray-800 border rounded px-2 py-1 text-xs text-gray-100 focus:outline-none focus:ring-1 ${
            slugInvalid ? 'border-red-500' : 'border-gray-700 focus:ring-blue-500/50'
          }`}
        />
      )}
      <div className="flex items-center gap-1">
        <button
          onClick={handleSave}
          disabled={saving || slugInvalid}
          className="text-emerald-400 hover:text-emerald-300 disabled:opacity-50"
          title="Save"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
        </button>
        <button onClick={onCancel} className="text-gray-500 hover:text-gray-300" title="Cancel">
          <X size={14} />
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MncCompaniesPage() {
  const [entries, setEntries] = useState<MncCompany[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);

  useEffect(() => {
    getMncCompanies()
      .then(setEntries)
      .catch(() => toast.error('Failed to load MNC list'))
      .finally(() => setLoading(false));
  }, []);

  function upsertLocal(updated: MncCompany) {
    setEntries((prev) => {
      const i = prev.findIndex((e) => e.id === updated.id);
      const next = i >= 0
        ? prev.map((e) => (e.id === updated.id ? updated : e))
        : [...prev, updated];
      return next.sort((a, b) => a.name.localeCompare(b.name));
    });
  }

  async function handleAdd(payload: { name: string; career_url: string; ats: MncAts; ats_slug?: string }) {
    setSaving(true);
    try {
      const entry = await addMncCompany({ ...payload, active: true });
      upsertLocal(entry);
      setShowForm(false);
      toast.success(`"${entry.name}" added`);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to add company';
      toast.error(typeof msg === 'string' ? msg : 'Failed to add company');
    } finally {
      setSaving(false);
    }
  }

  async function handleSave(id: string, patch: Partial<MncCompany>) {
    try {
      const updated = await updateMncCompany(id, {
        career_url: patch.career_url,
        ats: patch.ats,
        ats_slug: patch.ats_slug ?? null,
      });
      upsertLocal(updated);
      setEditingId(null);
      toast.success('Updated');
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to update';
      toast.error(typeof msg === 'string' ? msg : 'Failed to update');
    }
  }

  async function handleToggleActive(entry: MncCompany) {
    // For sentinel rows we call disable (creates shadow row); for tenant rows
    // we just flip active via PUT.
    if (entry.is_global && entry.active) {
      try {
        const shadow = await disableMncCompany(entry.id);
        // Replace the global row in the list with the shadow (same name).
        setEntries((prev) => {
          const filtered = prev.filter((e) => e.id !== entry.id);
          const dedup = filtered.filter(
            (e) => e.name.toLowerCase() !== shadow.name.toLowerCase(),
          );
          return [...dedup, shadow].sort((a, b) => a.name.localeCompare(b.name));
        });
        toast.success(`"${entry.name}" disabled for your tenant`);
      } catch {
        toast.error('Failed to disable');
      }
      return;
    }

    try {
      const updated = await updateMncCompany(entry.id, { active: !entry.active });
      upsertLocal(updated);
      toast.success(updated.active ? 'Enabled' : 'Disabled');
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Failed to toggle';
      toast.error(typeof msg === 'string' ? msg : 'Failed to toggle');
    }
  }

  async function handleDelete(entry: MncCompany) {
    if (entry.is_global) {
      // Global rows can't be deleted — offer to disable instead.
      if (!confirm(`"${entry.name}" is a global default. Disable it for your tenant?`)) return;
      await handleToggleActive(entry);
      return;
    }
    if (!confirm(`Remove "${entry.name}" from the MNC list?`)) return;
    try {
      await removeMncCompany(entry.id);
      setEntries((prev) => prev.filter((e) => e.id !== entry.id));
      toast.success(`"${entry.name}" removed`);
    } catch {
      toast.error('Failed to remove');
    }
  }

  const filtered = entries.filter((e) => {
    const q = search.toLowerCase();
    return (
      !q ||
      e.name.toLowerCase().includes(q) ||
      e.career_url.toLowerCase().includes(q) ||
      e.ats.toLowerCase().includes(q) ||
      (e.ats_slug ?? '').toLowerCase().includes(q)
    );
  });

  const activeCount = entries.filter((e) => e.active).length;

  return (
    <div className="p-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">MNC List</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Only the {activeCount} active companies on this list are scraped when you click <strong>Scrape MNC Jobs</strong>.
          </p>
        </div>
        {!showForm && (
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
            placeholder="Search name / URL / ATS / slug…"
            className="w-full sm:w-80 bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
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
          <div className="grid grid-cols-[1fr_2fr_auto_auto_auto_auto] gap-4 px-4 py-2.5 bg-gray-800/60 border-b border-gray-800 text-xs font-semibold text-gray-500 uppercase tracking-wide">
            <span>Company</span>
            <span>Career URL</span>
            <span>ATS · slug</span>
            <span>Source</span>
            <span>Active</span>
            <span className="w-16">Actions</span>
          </div>

          {filtered.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-gray-600">
              No results for &ldquo;{search}&rdquo;
            </div>
          ) : (
            filtered.map((entry, idx) => {
              const isEditing = editingId === entry.id;
              return (
                <div
                  key={entry.id}
                  className={`grid grid-cols-[1fr_2fr_auto_auto_auto_auto] gap-4 items-center px-4 py-3 ${
                    idx < filtered.length - 1 ? 'border-b border-gray-800/60' : ''
                  } ${entry.active ? '' : 'opacity-60'} hover:bg-gray-800/30 transition-colors group`}
                >
                  {/* Name */}
                  <span className={`text-sm font-medium truncate ${entry.active ? 'text-gray-200' : 'line-through text-gray-500'}`}>
                    {entry.name}
                  </span>

                  {/* Career URL — editable inline */}
                  {isEditing ? (
                    <div className="col-span-3">
                      <RowEditor
                        entry={entry}
                        onSave={handleSave}
                        onCancel={() => setEditingId(null)}
                      />
                    </div>
                  ) : (
                    <>
                      <a
                        href={entry.career_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-400 hover:text-blue-300 truncate flex items-center gap-1"
                        title={entry.career_url}
                      >
                        <ExternalLink size={11} className="shrink-0" />
                        <span className="truncate">{entry.career_url.replace(/^https?:\/\//, '')}</span>
                      </a>
                      <span className="text-xs text-gray-500 whitespace-nowrap">
                        <span className="text-gray-400">{entry.ats}</span>
                        {entry.ats_slug ? <span className="text-gray-600"> · {entry.ats_slug}</span> : null}
                      </span>
                    </>
                  )}

                  {/* Source badge */}
                  {!isEditing && (
                    <span
                      className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full whitespace-nowrap ${
                        entry.is_global
                          ? 'bg-gray-800 text-gray-400 border border-gray-700'
                          : 'bg-blue-900/40 text-blue-300 border border-blue-800'
                      }`}
                    >
                      {entry.is_global ? <Globe size={10} /> : <UserIcon size={10} />}
                      {entry.is_global ? 'Global' : 'Custom'}
                    </span>
                  )}

                  {/* Active toggle */}
                  {!isEditing && (
                    <button
                      onClick={() => handleToggleActive(entry)}
                      className={`flex items-center gap-1 text-xs px-2 py-1 rounded ${
                        entry.active
                          ? 'text-emerald-400 hover:bg-emerald-900/20'
                          : 'text-gray-500 hover:bg-gray-800'
                      }`}
                      title={entry.active ? 'Click to disable' : 'Click to enable'}
                    >
                      {entry.active ? <Eye size={13} /> : <EyeOff size={13} />}
                      {entry.active ? 'On' : 'Off'}
                    </button>
                  )}

                  {/* Actions */}
                  {!isEditing && (
                    <div className="flex items-center gap-2 w-16">
                      {!entry.is_global && (
                        <button
                          onClick={() => setEditingId(entry.id)}
                          className="text-gray-500 hover:text-blue-300 transition-colors opacity-0 group-hover:opacity-100"
                          title="Edit"
                        >
                          <Pencil size={13} />
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(entry)}
                        className="text-gray-600 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                        title={entry.is_global ? 'Disable for your tenant' : 'Remove'}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </div>
              );
            })
          )}

          {/* Footer */}
          <div className="px-4 py-2.5 border-t border-gray-800 bg-gray-800/30">
            <span className="text-xs text-gray-600">
              {filtered.length} {filtered.length === 1 ? 'company' : 'companies'}
              {search && ` matching "${search}"`}
              {' · '}
              <span className="text-emerald-500">{activeCount} active</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
