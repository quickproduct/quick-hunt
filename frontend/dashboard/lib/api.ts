import axios, { AxiosInstance } from 'axios';

const BASE_URL =
  typeof window !== 'undefined'
    ? '/api'
    : process.env.API_BASE_URL || 'http://localhost:8000';

// ── Token storage (localStorage — SSR-safe) ───────────────────────────────────

const TOKEN_KEY = 'jh_access_token';
const REFRESH_KEY = 'jh_refresh_token';

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}
export function getRefreshToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(REFRESH_KEY);
}
export function setTokens(access: string, refresh: string) {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}
export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

// ── Axios client ──────────────────────────────────────────────────────────────

export const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
});

// Request interceptor — attach Bearer token if available
apiClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor — auto-refresh on 401
let _isRefreshing = false;
let _refreshQueue: Array<{ resolve: (token: string) => void; reject: (error: unknown) => void }> = [];

apiClient.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }

    const refresh = getRefreshToken();
    if (!refresh) {
      clearTokens();
      return Promise.reject(error);
    }

    if (_isRefreshing) {
      return new Promise((resolve, reject) => {
        _refreshQueue.push({
          resolve: (token: string) => {
            original.headers['Authorization'] = `Bearer ${token}`;
            resolve(apiClient(original));
          },
          reject,
        });
      });
    }

    original._retry = true;
    _isRefreshing = true;

    try {
      const res = await axios.post(`${BASE_URL}/auth/refresh`, {
        refresh_token: refresh,
      });
      const { access_token, refresh_token } = res.data;
      setTokens(access_token, refresh_token);
      _refreshQueue.forEach((cb) => cb.resolve(access_token));
      _refreshQueue = [];
      original.headers['Authorization'] = `Bearer ${access_token}`;
      return apiClient(original);
    } catch (refreshError) {
      clearTokens();
      _refreshQueue.forEach((cb) => cb.reject(refreshError));
      _refreshQueue = [];
      return Promise.reject(error);
    } finally {
      _isRefreshing = false;
    }
  }
);

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Candidate {
  id: string;
  name: string;
  email: string;
  skills: string[];
  years_experience?: number;
  resume_url?: string;
  target_roles: string[];
  target_locations: string[];
  bio?: string;
  cover_letter_template?: string;
  static_cover_letter?: string;
  linkedin_url?: string;
  github_url?: string;
  is_active: boolean;
  created_at?: string;
}

export interface Job {
  id: string;
  candidate_id?: string;
  job_title: string;
  company: string;
  location?: string;
  job_description?: string;
  job_url: string;
  posted_date?: string;
  scraped_at?: string;
  hr_email?: string;
  company_website?: string;
  recruiter_name?: string;
  source_portal: string;
  status: string;
  dedupe_hash: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  job_type?: string;
  experience_required?: string;
  relevance_score?: number;
  score_breakdown?: Record<string, unknown>;
  cover_letter?: string;
  cover_letter_generated_at?: string;
}

export interface SkippedJob {
  job_id: string;
  reason: 'no_hr_email' | 'no_cover_letter' | 'already_sent' | 'not_found';
}

export interface BulkSendResult {
  queued: number;
  skipped: SkippedJob[];
  task_ids: string[];
  dry_run: boolean;
}

export interface SendLog {
  id: string;
  job_id: string;
  candidate_id: string;
  to_email: string;
  subject?: string;
  body_snippet?: string;
  status: string;
  provider?: string;
  provider_message_id?: string;
  sent_at?: string;
  delivered_at?: string;
  opened_at?: string;
  clicked_at?: string;
  error_message?: string;
  retry_count: number;
  job_title?: string;
  company?: string;
}

export interface Stats {
  total_jobs: number;
  jobs_by_status: Record<string, number>;
  jobs_by_portal: Record<string, number>;
  emails_sent: number;
  emails_delivered: number;
  emails_opened: number;
  emails_clicked: number;
  emails_bounced: number;
  emails_soft_bounced: number;
  cover_letters_generated: number;
  jobs_with_hr_email: number;
  jobs_ready: number;
  jobs_missing_hr: number;
  jobs_pending_approval: number;
}

export interface SearchTask {
  id: string;
  candidate_id: string;
  job_titles: string[];
  locations: string[];
  portals: string[];
  max_results_per_portal: number;
  status: string;
  jobs_found: number;
  created_at?: string;
  completed_at?: string;
  error?: string;
}

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  role: string;
  is_verified: boolean;
  is_active: boolean;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  plan: string;
  status: string;
  requires_approval: boolean;
  auto_send: boolean;
  score_threshold: number;
}

export interface Plan {
  id: string;
  label: string;
  price_inr: number;
  applications_per_day: number;
  ai_credits_per_month: number;
  active_automations: number;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export const authRegister = (data: {
  tenant_name: string;
  email: string;
  password: string;
}) =>
  apiClient.post<{ access_token: string; refresh_token: string }>('/auth/register', data).then((r) => {
    setTokens(r.data.access_token, r.data.refresh_token);
    return r.data;
  });

export const authLogin = (data: { email: string; password: string }) =>
  apiClient.post<{ access_token: string; refresh_token: string }>('/auth/login', data).then((r) => {
    setTokens(r.data.access_token, r.data.refresh_token);
    return r.data;
  });

export const authLogout = () => {
  const refresh = getRefreshToken();
  clearTokens();
  if (refresh) apiClient.post('/auth/logout', { refresh_token: refresh }).catch(() => {});
};

export const verifyEmail = (token: string) =>
  apiClient.post('/auth/verify-email', { token });

export const forgotPassword = (email: string) =>
  apiClient.post('/auth/forgot-password', { email });

export const resetPassword = (token: string, new_password: string) =>
  apiClient.post('/auth/reset-password', { token, new_password });

// ── User / Tenant ─────────────────────────────────────────────────────────────

export const getMe = () => apiClient.get<User>('/users/me').then((r) => r.data);

export const updateMe = (data: Partial<{ email: string; current_password: string; new_password: string }>) =>
  apiClient.put<User>('/users/me', data).then((r) => r.data);

export const getMyTenant = () => apiClient.get<Tenant>('/tenants/me').then((r) => r.data);

export const updateMyTenant = (data: Partial<Tenant>) =>
  apiClient.put<Tenant>('/tenants/me', data).then((r) => r.data);

export const getTenantUsage = () =>
  apiClient.get('/tenants/me/usage').then((r) => r.data);

// ── Billing ───────────────────────────────────────────────────────────────────

export const getPlans = () => apiClient.get<Plan[]>('/billing/plans').then((r) => r.data);

export const getSubscription = () =>
  apiClient.get('/billing/subscription').then((r) => r.data);

export const createCheckout = (plan: string) =>
  apiClient.post<{ payment_link_url: string; plan: string }>(`/billing/create-checkout?plan=${plan}`).then((r) => r.data);

export const cancelSubscription = () => apiClient.post('/billing/cancel');

export const verifyCallback = (params: {
  razorpay_payment_id: string;
  razorpay_payment_link_id: string;
  razorpay_payment_link_reference_id: string;
  razorpay_payment_link_status: string;
  razorpay_signature: string;
}) =>
  apiClient
    .post<{ activated: boolean; plan?: string }>('/billing/verify-callback', params)
    .then((r) => r.data);

// ── Candidates ────────────────────────────────────────────────────────────────

let _candidatesCache: { data: Candidate[]; ts: number } | null = null;
let _candidatesInflight: Promise<Candidate[]> | null = null;
const _CANDIDATES_TTL_MS = 5 * 60 * 1000;

export function invalidateCandidatesCache() {
  _candidatesCache = null;
}

export const getCandidates = (): Promise<Candidate[]> => {
  const now = Date.now();
  if (_candidatesCache && now - _candidatesCache.ts < _CANDIDATES_TTL_MS) {
    return Promise.resolve(_candidatesCache.data);
  }
  if (_candidatesInflight) return _candidatesInflight;

  _candidatesInflight = apiClient
    .get<Candidate[]>('/candidates')
    .then((r) => {
      _candidatesCache = { data: r.data, ts: Date.now() };
      return r.data;
    })
    .finally(() => {
      _candidatesInflight = null;
    });
  return _candidatesInflight;
};

export const createCandidate = (data: Partial<Candidate>) =>
  apiClient.post<Candidate>('/candidates', data).then((r) => {
    invalidateCandidatesCache();
    return r.data;
  });

export const updateCandidate = (id: string, data: Partial<Candidate>) =>
  apiClient.put<Candidate>(`/candidates/${id}`, data).then((r) => {
    invalidateCandidatesCache();
    return r.data;
  });

export const uploadResume = (id: string, file: File): Promise<Candidate> => {
  const form = new FormData();
  form.append('file', file);
  return apiClient
    .post<Candidate>(`/candidates/${id}/resume`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((r) => {
      invalidateCandidatesCache();
      return r.data;
    });
};

export const downloadResumeUrl = (id: string) => `/api/candidates/${id}/resume`;

export const directHRSend = (
  candidateId: string,
  hrEmails: string[]
): Promise<{ sent: number; failed: string[]; skipped: string[] }> =>
  apiClient
    .post<{ sent: number; failed: string[]; skipped: string[] }>('/direct-send', {
      candidate_id: candidateId,
      hr_emails: hrEmails,
    })
    .then((r) => r.data);

// ── Jobs ──────────────────────────────────────────────────────────────────────

export const getJobs = (params?: Record<string, unknown>, signal?: AbortSignal) =>
  apiClient.get<Job[]>('/jobs', { params, signal }).then((r) => r.data);

export const getJob = (id: string) =>
  apiClient.get<Job>(`/jobs/${id}`).then((r) => r.data);

export const updateJobStatus = (id: string, status: string) =>
  apiClient.patch(`/jobs/${id}/status`, { status }).then((r) => r.data);

export const setJobHrEmail = (id: string, hrEmail: string): Promise<Job> =>
  apiClient.patch<Job>(`/jobs/${id}/hr-email`, { hr_email: hrEmail }).then((r) => r.data);

export const resetEmailDiscovery = (): Promise<{ reset: number; message: string }> =>
  apiClient.post<{ reset: number; message: string }>('/admin/reset-email-discovery').then((r) => r.data);

export const approveJob = (id: string) =>
  apiClient.post(`/jobs/${id}/approve`).then((r) => r.data);

export const generateCoverLetter = (id: string, candidateId: string, tone = 'professional') =>
  apiClient.post(`/jobs/${id}/generate_cover`, { candidate_id: candidateId, tone }).then((r) => r.data);

export const sendApplication = (
  jobId: string,
  data: {
    candidate_id: string;
    override_email?: string;
    override_subject?: string;
    attach_resume?: boolean;
    dry_run?: boolean;
  },
  coverLetterOverride?: string
) => {
  const payload: Record<string, unknown> = { ...data };
  if (coverLetterOverride) {
    payload.cover_letter = coverLetterOverride;
  }
  return apiClient.post(`/jobs/${jobId}/send`, payload).then((r) => r.data);
};

export const bulkSendApplications = (
  jobIds: string[],
  candidateId: string,
  opts: { attach_resume?: boolean; dry_run?: boolean } = {}
): Promise<BulkSendResult> =>
  apiClient
    .post('/jobs/bulk_send', {
      job_ids: jobIds,
      candidate_id: candidateId,
      attach_resume: opts.attach_resume ?? true,
      dry_run: opts.dry_run ?? false,
    })
    .then((r) => r.data);

export const bulkGenerateCovers = (
  jobIds: string[],
  candidateId: string,
  tone = 'professional'
): Promise<{ queued: number; not_found: string[]; task_ids: string[] }> =>
  apiClient
    .post('/jobs/bulk_generate_cover', { job_ids: jobIds, candidate_id: candidateId, tone })
    .then((r) => r.data);

export const getJobsCount = (
  params?: Record<string, unknown>,
  signal?: AbortSignal
): Promise<{ count: number }> =>
  apiClient.get('/jobs/count', { params, signal }).then((r) => r.data);

export const getJobIds = (
  params?: Record<string, unknown>,
  signal?: AbortSignal
): Promise<string[]> =>
  apiClient.get('/jobs/ids', { params, signal }).then((r) => r.data);

// ── Search ────────────────────────────────────────────────────────────────────

export const triggerSearch = (data: {
  job_titles: string[];
  locations: string[];
  portals: string[];
  max_results_per_portal: number;
  candidate_id: string;
  auto_generate_covers: boolean;
}) => apiClient.post('/search', data).then((r) => r.data);

export const getSearchTask = (id: string) =>
  apiClient.get<SearchTask>(`/search/tasks/${id}`).then((r) => r.data);

// ── Send logs ─────────────────────────────────────────────────────────────────

export const getSendLogs = (params?: Record<string, unknown>) =>
  apiClient.get<SendLog[]>('/jobs/send_logs', { params }).then((r) => r.data);

export interface TimelineEvent {
  event: string;
  label: string;
  timestamp: string | null;
  done: boolean;
  metadata?: Record<string, unknown> | null;
}

export interface JobTimeline {
  job_id: string;
  events: TimelineEvent[];
}

export const getJobTimeline = (jobId: string) =>
  apiClient.get<JobTimeline>(`/jobs/${jobId}/timeline`).then((r) => r.data);

// ── Search tasks ──────────────────────────────────────────────────────────────

export const getSearchTasks = (limit = 5) =>
  apiClient.get<SearchTask[]>('/search/tasks', { params: { limit } }).then((r) => r.data);

// ── Stats ─────────────────────────────────────────────────────────────────────

export const getStats = (params?: { candidate_id?: string }) =>
  apiClient.get<Stats>('/stats', { params }).then((r) => r.data);

// ── Team / Users ──────────────────────────────────────────────────────────────

export const listUsers = () =>
  apiClient.get<User[]>('/users').then((r) => r.data);

export const inviteUser = (data: { email: string; role: string }) =>
  apiClient.post<{ id: string; email: string; role: string }>('/users/invite', data).then((r) => r.data);

export const removeUser = (userId: string) =>
  apiClient.delete(`/users/${userId}`);

export const changeUserRole = (userId: string, role: string) =>
  apiClient.patch<User>(`/users/${userId}/role`, { role }).then((r) => r.data);

// ── Blacklist ─────────────────────────────────────────────────────────────────

export interface BlacklistedCompany {
  id: string;
  name: string;
  reason: string | null;
  created_at: string;
}

export const getBlacklist = () =>
  apiClient.get<BlacklistedCompany[]>('/blacklist').then((r) => r.data);

export const addToBlacklist = (data: { name: string; reason?: string }) =>
  apiClient.post<BlacklistedCompany>('/blacklist', data).then((r) => r.data);

export const updateBlacklistEntry = (id: string, data: { reason?: string | null }) =>
  apiClient.put<BlacklistedCompany>(`/blacklist/${id}`, data).then((r) => r.data);

export const removeFromBlacklist = (id: string) =>
  apiClient.delete(`/blacklist/${id}`);

// ── MNC Jobs ──────────────────────────────────────────────────────────────────

export const getMncJobs = (params?: Record<string, unknown>) =>
  getJobs({ ...params, mnc_only: true });

export const getMncJobsCount = (params?: Record<string, unknown>) =>
  getJobsCount({ ...params, mnc_only: true });

export const getMncJobIds = (params?: Record<string, unknown>) =>
  getJobIds({ ...params, mnc_only: true });

export const triggerMncScrape = (candidateId?: string) =>
  apiClient
    .post<{ task_id: string; dispatch_id: string; status: string; portal: string }>(
      '/jobs/trigger-mnc-scrape',
      null,
      { params: candidateId ? { candidate_id: candidateId } : undefined },
    )
    .then((r) => r.data);

export interface MncScrapeProgress {
  dispatch_id: string | null;
  candidate_id: string | null;
  total: number;
  done: number;
  saved: number;
  started_at?: string | null;
  finished_at?: string | null;
  final_saved?: number | null;
  final_errors?: number;
  final_timeouts?: number;
}

export interface MncScrapeStatus {
  in_flight: boolean;
  progress: MncScrapeProgress | null;
}

export const getMncScrapeStatus = () =>
  apiClient.get<MncScrapeStatus>('/jobs/mnc-scrape-status').then((r) => r.data);

// ── MNC Company List (user-managed scraping roster) ──────────────────────────

export type MncAts =
  | 'greenhouse' | 'lever' | 'smartrecruiters' | 'workday'
  | 'icims' | 'taleo' | 'bamboohr' | 'custom';

export interface MncCompany {
  id: string;
  name: string;
  career_url: string;
  ats: MncAts;
  ats_slug: string | null;
  active: boolean;
  is_global: boolean;
  created_at: string;
  updated_at: string;
}

export interface MncCompanyCreate {
  name: string;
  career_url: string;
  ats: MncAts;
  ats_slug?: string | null;
  active?: boolean;
}

export interface MncCompanyUpdate {
  name?: string;
  career_url?: string;
  ats?: MncAts;
  ats_slug?: string | null;
  active?: boolean;
}

export const getMncCompanies = () =>
  apiClient.get<MncCompany[]>('/mnc-companies').then((r) => r.data);

export const addMncCompany = (data: MncCompanyCreate) =>
  apiClient.post<MncCompany>('/mnc-companies', data).then((r) => r.data);

export const updateMncCompany = (id: string, data: MncCompanyUpdate) =>
  apiClient.put<MncCompany>(`/mnc-companies/${id}`, data).then((r) => r.data);

export const removeMncCompany = (id: string) =>
  apiClient.delete(`/mnc-companies/${id}`);

// Shadow-disable a global default (creates / flips a tenant row with active=false).
export const disableMncCompany = (id: string) =>
  apiClient.post<MncCompany>(`/mnc-companies/${id}/disable`).then((r) => r.data);

// ── Consulting / IT Outsourcing Jobs ─────────────────────────────────────────

export const getConsultingJobs = (params?: Record<string, unknown>) =>
  getJobs({ ...params, consulting_only: true });

export const getConsultingJobsCount = (params?: Record<string, unknown>) =>
  getJobsCount({ ...params, consulting_only: true });

export const getConsultingJobIds = (params?: Record<string, unknown>) =>
  getJobIds({ ...params, consulting_only: true });

export const triggerConsultingScrape = (candidateId?: string) =>
  apiClient
    .post<{ task_id: string; dispatch_id: string; status: string; portal: string }>(
      '/jobs/trigger-consulting-scrape',
      null,
      { params: candidateId ? { candidate_id: candidateId } : undefined },
    )
    .then((r) => r.data);

export interface ConsultingScrapeProgress {
  dispatch_id: string | null;
  candidate_id: string | null;
  total: number;
  done: number;
  saved: number;
  started_at?: string | null;
  finished_at?: string | null;
  final_saved?: number | null;
  final_errors?: number;
  final_timeouts?: number;
}

export interface ConsultingScrapeStatus {
  in_flight: boolean;
  progress: ConsultingScrapeProgress | null;
}

export const getConsultingScrapeStatus = () =>
  apiClient.get<ConsultingScrapeStatus>('/jobs/consulting-scrape-status').then((r) => r.data);

// ── Consulting Company List (user-managed scraping roster) ───────────────────

export type ConsultingAts = MncAts;

export interface ConsultingCompany {
  id: string;
  name: string;
  career_url: string;
  ats: ConsultingAts;
  ats_slug: string | null;
  active: boolean;
  is_global: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConsultingCompanyCreate {
  name: string;
  career_url: string;
  ats: ConsultingAts;
  ats_slug?: string | null;
  active?: boolean;
}

export interface ConsultingCompanyUpdate {
  name?: string;
  career_url?: string;
  ats?: ConsultingAts;
  ats_slug?: string | null;
  active?: boolean;
}

export const getConsultingCompanies = () =>
  apiClient.get<ConsultingCompany[]>('/consulting-companies').then((r) => r.data);

export const addConsultingCompany = (data: ConsultingCompanyCreate) =>
  apiClient.post<ConsultingCompany>('/consulting-companies', data).then((r) => r.data);

export const updateConsultingCompany = (id: string, data: ConsultingCompanyUpdate) =>
  apiClient.put<ConsultingCompany>(`/consulting-companies/${id}`, data).then((r) => r.data);

export const removeConsultingCompany = (id: string) =>
  apiClient.delete(`/consulting-companies/${id}`);

export const disableConsultingCompany = (id: string) =>
  apiClient.post<ConsultingCompany>(`/consulting-companies/${id}/disable`).then((r) => r.data);

// ── HR Emails ─────────────────────────────────────────────────────────────────

export interface HrEmail {
  id: string;
  tenant_id: string;
  email: string;
  domain: string;
  job_count: number;
  send_count: number;
  delivered_count: number;
  opened_count: number;
  clicked_count: number;
  hard_bounce_count: number;
  soft_bounce_count: number;
  blocked_count: number;
  spam_count: number;
  last_send_at?: string;
  last_bounce_at?: string;
  last_bounce_type?: string;
  last_bounce_reason?: string;
  mx_valid?: boolean;
  mx_checked_at?: string;
  validation_status: 'unknown' | 'valid' | 'invalid' | 'bounced' | 'fake';
  is_placeholder: boolean;
  first_seen_at?: string;
  last_seen_at?: string;
}

export interface HrEmailStats {
  total_unique: number;
  valid_count: number;
  valid_pct: number;
  bounced_count: number;
  bounce_rate: number;
  fake_count: number;
  unknown_count: number;
  domains_with_bounces: number;
  total_sends: number;
  total_delivered: number;
}

export interface DomainAnalysisRow {
  domain: string;
  email_count: number;
  send_count: number;
  bounce_count: number;
  bounce_rate: number;
  mx_valid: boolean | null;
}

export const getHrEmails = (params?: Record<string, unknown>): Promise<HrEmail[]> =>
  apiClient.get<HrEmail[]>('/hr-emails', { params }).then((r) => r.data);

export const getHrEmailStats = (): Promise<HrEmailStats> =>
  apiClient.get<HrEmailStats>('/hr-emails/stats').then((r) => r.data);

export const getHrEmailDomainAnalysis = (params?: Record<string, unknown>): Promise<DomainAnalysisRow[]> =>
  apiClient.get<DomainAnalysisRow[]>('/hr-emails/domain-analysis', { params }).then((r) => r.data);

export const triggerHrEmailBackfill = (): Promise<{ task_id: string; status: string }> =>
  apiClient.post('/hr-emails/backfill').then((r) => r.data);

export const validateHrEmailMx = (emailId: string): Promise<{ task_id: string; domain: string }> =>
  apiClient.post(`/hr-emails/${emailId}/validate`).then((r) => r.data);

export const updateHrEmail = (emailId: string, data: { validation_status?: string }): Promise<HrEmail> =>
  apiClient.patch<HrEmail>(`/hr-emails/${emailId}`, data).then((r) => r.data);

export interface BrevoImportResult {
  total_rows: number;
  unique_messages: number;
  unique_emails: number;
  send_logs_updated: number;
  jobs_updated: number;
  hr_emails_upserted: number;
  unmatched_messages: number;
}

export const importBrevoCSV = (file: File): Promise<BrevoImportResult> => {
  const form = new FormData();
  form.append('file', file);
  return apiClient
    .post<BrevoImportResult>('/hr-emails/import-brevo-csv', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    })
    .then((r) => r.data);
};
