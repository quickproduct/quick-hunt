'use client';

import { useState, useEffect, useRef } from 'react';
import {
  UserPlus,
  Pencil,
  X,
  Loader2,
  Users,
  Linkedin,
  Github,
  ChevronDown,
  ChevronUp,
  Check,
  Plus,
  Upload,
  Download,
  FileText,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getCandidates,
  createCandidate,
  updateCandidate,
  uploadResume,
  downloadResumeUrl,
  type Candidate,
} from '@/lib/api';

// ── Helpers ───────────────────────────────────────────────────────────────────

function avatarColor(name: string) {
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
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length];
}

function initials(name: string) {
  return name
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

// ── Tag input ─────────────────────────────────────────────────────────────────

function TagInput({
  label,
  placeholder,
  tags,
  onChange,
}: {
  label: string;
  placeholder: string;
  tags: string[];
  onChange: (tags: string[]) => void;
}) {
  const [input, setInput] = useState('');

  const add = () => {
    const val = input.trim();
    if (val && !tags.includes(val)) onChange([...tags, val]);
    setInput('');
  };

  const remove = (tag: string) => onChange(tags.filter((t) => t !== tag));

  return (
    <div>
      <label className="block text-xs font-medium text-gray-400 mb-1.5">{label}</label>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {tags.map((tag) => (
          <span
            key={tag}
            className="flex items-center gap-1 bg-blue-500/15 text-blue-300 border border-blue-500/25 text-xs px-2 py-0.5 rounded-full"
          >
            {tag}
            <button
              type="button"
              onClick={() => remove(tag)}
              className="hover:text-white transition-colors"
            >
              <X size={10} />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              add();
            }
          }}
          placeholder={placeholder}
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
        />
        <button
          type="button"
          onClick={add}
          className="px-2.5 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg transition-colors"
        >
          <Plus size={14} />
        </button>
      </div>
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6 text-center">
      <div className="w-16 h-16 rounded-2xl bg-gray-800 flex items-center justify-center mb-4">
        <Users size={28} className="text-gray-600" />
      </div>
      <h3 className="text-sm font-semibold text-gray-300 mb-1">No candidates yet</h3>
      <p className="text-xs text-gray-500 mb-5 max-w-xs">
        Candidates are job seekers whose applications are automated. Add a profile to get started.
      </p>
      <button
        onClick={onAdd}
        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
      >
        <UserPlus size={14} />
        Add candidate
      </button>
    </div>
  );
}

// ── Candidate form ────────────────────────────────────────────────────────────

type FormData = {
  name: string;
  email: string;
  bio: string;
  cover_letter_template: string;
  static_cover_letter: string;
  years_experience: string;
  linkedin_url: string;
  github_url: string;
  skills: string[];
  target_roles: string[];
  target_locations: string[];
};

const EMPTY_FORM: FormData = {
  name: '',
  email: '',
  bio: '',
  cover_letter_template: '',
  static_cover_letter: '',
  years_experience: '',
  linkedin_url: '',
  github_url: '',
  skills: [],
  target_roles: [],
  target_locations: [],
};

function candidateToForm(c: Candidate): FormData {
  return {
    name: c.name,
    email: c.email,
    bio: c.bio ?? '',
    cover_letter_template: c.cover_letter_template ?? '',
    static_cover_letter: c.static_cover_letter ?? '',
    years_experience: c.years_experience != null ? String(c.years_experience) : '',
    linkedin_url: c.linkedin_url ?? '',
    github_url: c.github_url ?? '',
    skills: c.skills ?? [],
    target_roles: c.target_roles ?? [],
    target_locations: c.target_locations ?? [],
  };
}

function ResumeUploader({
  candidateId,
  existingResume,
  onUploaded,
}: {
  candidateId: string | null;
  existingResume: string | null;
  onUploaded: (updated: Candidate) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  const hasResume = !!(existingResume || pendingFile);

  const handleFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('Only PDF files are accepted');
      return;
    }
    setPendingFile(file);
    if (candidateId) {
      doUpload(file, candidateId);
    }
  };

  const doUpload = async (file: File, id: string) => {
    setUploading(true);
    try {
      const updated = await uploadResume(id, file);
      onUploaded(updated);
      setPendingFile(null);
      toast.success('Resume uploaded');
    } catch {
      toast.error('Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  return (
    <div>
      <label className="block text-xs font-medium text-gray-400 mb-1.5">Resume (PDF)</label>

      {hasResume ? (
        <div className="flex items-center gap-3 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5">
          <FileText size={16} className="text-green-400 shrink-0" />
          <span className="text-sm text-gray-200 flex-1 truncate">
            {pendingFile ? pendingFile.name : (existingResume?.split('/').pop() ?? 'resume.pdf')}
          </span>
          <div className="flex items-center gap-2 shrink-0">
            {candidateId && existingResume && (
              <a
                href={downloadResumeUrl(candidateId)}
                download
                className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
              >
                <Download size={13} />
                Download
              </a>
            )}
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
            >
              {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
              Replace
            </button>
          </div>
        </div>
      ) : (
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
          className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-gray-700 hover:border-blue-500/50 rounded-lg px-4 py-5 cursor-pointer transition-colors group"
        >
          {uploading ? (
            <Loader2 size={20} className="text-blue-400 animate-spin" />
          ) : (
            <Upload size={20} className="text-gray-500 group-hover:text-blue-400 transition-colors" />
          )}
          <p className="text-xs text-gray-500 group-hover:text-gray-300 transition-colors text-center">
            {uploading ? 'Uploading…' : 'Click or drag & drop a PDF resume'}
          </p>
          {!candidateId && (
            <p className="text-xs text-yellow-500/80">Save the candidate first, then upload resume</p>
          )}
        </div>
      )}

      <input
        ref={fileRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = '';
        }}
      />
    </div>
  );
}

function CandidateForm({
  initial,
  editTarget,
  onSave,
  onCancel,
  saving,
}: {
  initial: FormData;
  editTarget: Candidate | null;
  onSave: (data: FormData) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<FormData>(initial);
  const [showOptional, setShowOptional] = useState(false);
  const [currentCandidate, setCurrentCandidate] = useState<Candidate | null>(editTarget);

  const set = (key: keyof FormData, value: string | string[]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave(form);
      }}
      className="space-y-4"
    >
      {/* Required fields */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">
            Full name <span className="text-red-400">*</span>
          </label>
          <input
            required
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="Suraj Shetty"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">
            Email <span className="text-red-400">*</span>
          </label>
          <input
            required
            type="email"
            value={form.email}
            onChange={(e) => set('email', e.target.value)}
            placeholder="suraj@example.com"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
          />
        </div>
      </div>

      <TagInput
        label="Skills"
        placeholder="PHP, Laravel, MySQL... (press Enter)"
        tags={form.skills}
        onChange={(v) => set('skills', v)}
      />

      <TagInput
        label="Target roles"
        placeholder="PHP Developer, Laravel Engineer..."
        tags={form.target_roles}
        onChange={(v) => set('target_roles', v)}
      />

      <TagInput
        label="Target locations"
        placeholder="Remote, Mumbai, Bangalore..."
        tags={form.target_locations}
        onChange={(v) => set('target_locations', v)}
      />

      {/* Optional fields toggle */}
      <button
        type="button"
        onClick={() => setShowOptional((p) => !p)}
        className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors"
      >
        {showOptional ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        {showOptional ? 'Hide optional fields' : 'Show optional fields'}
      </button>

      {showOptional && (
        <div className="space-y-4 pt-1">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">
                Years of experience
              </label>
              <input
                type="number"
                min={0}
                max={50}
                value={form.years_experience}
                onChange={(e) => set('years_experience', e.target.value)}
                placeholder="3"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
              />
            </div>
            <ResumeUploader
              candidateId={currentCandidate?.id ?? null}
              existingResume={currentCandidate?.resume_url ?? null}
              onUploaded={(updated) => setCurrentCandidate(updated)}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">LinkedIn URL</label>
              <input
                type="url"
                value={form.linkedin_url}
                onChange={(e) => set('linkedin_url', e.target.value)}
                placeholder="https://linkedin.com/in/..."
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">GitHub URL</label>
              <input
                type="url"
                value={form.github_url}
                onChange={(e) => set('github_url', e.target.value)}
                placeholder="https://github.com/..."
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">Bio / summary</label>
            <textarea
              rows={3}
              value={form.bio}
              onChange={(e) => set('bio', e.target.value)}
              placeholder="Brief description of experience and career goals..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 resize-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">
              Custom cover letter template
            </label>
            <p className="text-xs text-gray-500 mb-1.5">
              Write your own cover letter. Use{' '}
              <code className="bg-gray-800 text-blue-300 px-1 rounded">{'{job-title}'}</code> and{' '}
              <code className="bg-gray-800 text-blue-300 px-1 rounded">{'{company-name}'}</code> as
              placeholders — they will be replaced for each application. When set, this overrides AI
              generation.
            </p>
            <textarea
              rows={8}
              value={form.cover_letter_template}
              onChange={(e) => set('cover_letter_template', e.target.value)}
              placeholder={`Dear Hiring Manager,\n\nI am writing to apply for the {job-title} position at {company-name}...\n\nBest regards,\n${form.name || 'Your Name'}`}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 resize-y font-mono"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">
              Static email cover letter
            </label>
            <p className="text-xs text-gray-500 mb-1.5">
              A fixed cover letter with no dynamic fields. Used when sending directly to HR emails
              via the <strong className="text-gray-400">Direct HR Send</strong> page.
            </p>
            <textarea
              rows={8}
              value={form.static_cover_letter}
              onChange={(e) => set('static_cover_letter', e.target.value)}
              placeholder={`Dear Hiring Manager,\n\nI am writing to express my interest in joining your team...\n\nBest regards,\n${form.name || 'Your Name'}`}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 resize-y font-mono"
            />
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-2">
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
          Save
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="bg-gray-800 hover:bg-gray-700 text-gray-300 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

// ── Candidate card ────────────────────────────────────────────────────────────

function CandidateCard({
  candidate,
  onEdit,
}: {
  candidate: Candidate;
  onEdit: (c: Candidate) => void;
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition-colors">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`w-11 h-11 rounded-full flex items-center justify-center text-white text-sm font-bold shrink-0 ${avatarColor(candidate.name)}`}
          >
            {initials(candidate.name)}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-gray-100 truncate">{candidate.name}</p>
            <p className="text-xs text-gray-500 truncate">{candidate.email}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              candidate.is_active
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25'
                : 'bg-gray-700/50 text-gray-500 border border-gray-700'
            }`}
          >
            {candidate.is_active ? 'Active' : 'Inactive'}
          </span>
          <button
            onClick={() => onEdit(candidate)}
            className="p-1.5 text-gray-500 hover:text-blue-400 hover:bg-blue-500/10 rounded-md transition-colors"
            title="Edit candidate"
          >
            <Pencil size={13} />
          </button>
        </div>
      </div>

      {/* Skills */}
      {candidate.skills.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {candidate.skills.slice(0, 6).map((s) => (
            <span
              key={s}
              className="text-xs px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20"
            >
              {s}
            </span>
          ))}
          {candidate.skills.length > 6 && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-500">
              +{candidate.skills.length - 6}
            </span>
          )}
        </div>
      )}

      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500">
        {candidate.years_experience != null && (
          <span>{candidate.years_experience} yr{candidate.years_experience !== 1 ? 's' : ''} exp</span>
        )}
        {candidate.target_roles.length > 0 && (
          <span className="truncate max-w-[160px]">{candidate.target_roles[0]}{candidate.target_roles.length > 1 ? ` +${candidate.target_roles.length - 1}` : ''}</span>
        )}
        {candidate.target_locations.length > 0 && (
          <span>{candidate.target_locations[0]}{candidate.target_locations.length > 1 ? ` +${candidate.target_locations.length - 1}` : ''}</span>
        )}
      </div>

      {/* Links + resume download */}
      {(candidate.linkedin_url || candidate.github_url || candidate.resume_url) && (
        <div className="flex items-center gap-3 mt-3 pt-3 border-t border-gray-800 flex-wrap">
          {candidate.linkedin_url && (
            <a
              href={candidate.linkedin_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-blue-400 transition-colors"
            >
              <Linkedin size={12} />
              LinkedIn
            </a>
          )}
          {candidate.github_url && (
            <a
              href={candidate.github_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              <Github size={12} />
              GitHub
            </a>
          )}
          {candidate.resume_url && (
            <a
              href={downloadResumeUrl(candidate.id)}
              download
              className="flex items-center gap-1.5 text-xs text-emerald-500 hover:text-emerald-400 transition-colors ml-auto"
            >
              <Download size={12} />
              Resume
            </a>
          )}
        </div>
      )}
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function CardSkeleton() {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 animate-pulse">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-11 h-11 rounded-full bg-gray-800" />
        <div className="space-y-1.5">
          <div className="h-3.5 bg-gray-800 rounded w-32" />
          <div className="h-3 bg-gray-800 rounded w-44" />
        </div>
      </div>
      <div className="flex gap-1.5 mb-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-5 bg-gray-800 rounded-full w-16" />
        ))}
      </div>
      <div className="h-3 bg-gray-800 rounded w-40" />
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CandidatesPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState<Candidate | null>(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setCandidates(await getCandidates());
    } catch {
      toast.error('Failed to load candidates.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openAdd = () => {
    setEditTarget(null);
    setShowForm(true);
  };

  const openEdit = (c: Candidate) => {
    setEditTarget(c);
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditTarget(null);
  };

  const handleSave = async (form: FormData) => {
    setSaving(true);
    try {
      const payload: Partial<Candidate> = {
        name: form.name,
        email: form.email,
        bio: form.bio || undefined,
        cover_letter_template: form.cover_letter_template || undefined,
        static_cover_letter: form.static_cover_letter || undefined,
        years_experience: form.years_experience ? Number(form.years_experience) : undefined,
        linkedin_url: form.linkedin_url || undefined,
        github_url: form.github_url || undefined,
        skills: form.skills,
        target_roles: form.target_roles,
        target_locations: form.target_locations,
      };

      if (editTarget) {
        await updateCandidate(editTarget.id, payload);
        toast.success(`${form.name} updated.`);
      } else {
        await createCandidate(payload);
        toast.success(`${form.name} added as a candidate.`);
      }
      closeForm();
      await load();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to save candidate.';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Candidates</h1>
          <p className="text-sm text-gray-500 mt-1">
            Job seekers whose applications are automated by this system
          </p>
        </div>
        <button
          onClick={openAdd}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <UserPlus size={15} />
          Add candidate
        </button>
      </div>

      {/* Info callout */}
      <div className="mb-6 p-3 bg-blue-500/8 border border-blue-500/20 rounded-lg text-xs text-blue-300">
        <strong className="font-semibold">Candidates vs Team members:</strong> Candidates are job
        seekers (e.g. Suraj Shetty, Gunjan Pandey) whose job applications are automated here.
        Team members are colleagues who log in to manage this dashboard — found under{' '}
        <strong>Account → Team</strong>.
      </div>

      {/* Form panel */}
      <div
        className={`overflow-hidden transition-all duration-300 ${
          showForm ? 'max-h-[1600px] opacity-100 mb-6' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="bg-gray-900 border border-blue-500/30 rounded-xl p-6">
          <div className="flex items-center justify-between mb-5">
            <h3 className="text-sm font-semibold text-gray-200">
              {editTarget ? `Edit — ${editTarget.name}` : 'Add new candidate'}
            </h3>
            <button
              onClick={closeForm}
              className="text-gray-500 hover:text-gray-300 transition-colors"
            >
              <X size={16} />
            </button>
          </div>
          <CandidateForm
            key={editTarget?.id ?? 'new'}
            initial={editTarget ? candidateToForm(editTarget) : EMPTY_FORM}
            editTarget={editTarget}
            onSave={handleSave}
            onCancel={closeForm}
            saving={saving}
          />
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : candidates.length === 0 ? (
        <EmptyState onAdd={openAdd} />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {candidates.map((c) => (
            <CandidateCard key={c.id} candidate={c} onEdit={openEdit} />
          ))}
        </div>
      )}

      {/* Count */}
      {!loading && candidates.length > 0 && (
        <p className="text-xs text-gray-600 mt-4 text-right">
          {candidates.length} candidate{candidates.length !== 1 ? 's' : ''}
        </p>
      )}
    </div>
  );
}
