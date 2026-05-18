// API Types (matching backend schemas)
export interface User {
  id: string;
  tenant_id?: string;
  email: string;
  role?: string;
  is_verified?: boolean;
  is_active?: boolean;
  name?: string;
  created_at?: string;
  updated_at?: string;
}

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
  updated_at?: string;
}

export type JobStatus =
  | 'new'
  | 'scoring'
  | 'filtered'
  | 'pending_approval'
  | 'cover_generated'
  | 'sending'
  | 'sent'
  | 'applied'
  | 'bounced'
  | 'ignored'
  | 'error';

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
  status: JobStatus;
  dedupe_hash: string;
  salary_min?: number;
  salary_max?: number;
  salary_currency?: string;
  job_type?: string;
  experience_required?: string;
  raw_data?: any;
  relevance_score?: number;
  score_breakdown?: Record<string, unknown>;
  cover_letter?: string;
  cover_letter_generated_at?: string;
}

export type SendLogStatus =
  | 'queued'
  | 'sent'
  | 'deferred'
  | 'soft_bounced'
  | 'blocked'
  | 'delivered'
  | 'opened'
  | 'clicked'
  | 'bounced'
  | 'failed'
  | 'dry_run';

export interface SendLog {
  id: string;
  job_id: string;
  candidate_id: string;
  to_email: string;
  subject?: string;
  body_snippet?: string;
  status: SendLogStatus;
  provider?: string;
  provider_message_id?: string;
  sent_at?: string;
  delivered_at?: string;
  opened_at?: string;
  clicked_at?: string;
  error_message?: string;
  response_webhook_payload?: any;
  retry_count: number;
  job_title?: string;
  company?: string;
}

export interface SearchTask {
  id: string;
  candidate_id: string;
  job_titles: string[];
  locations: string[];
  portals: string[];
  max_results_per_portal: number;
  status: 'queued' | 'running' | 'completed' | 'error';
  jobs_found: number;
  tasks_total: number;
  tasks_completed: number;
  started_at?: string;
  completed_at?: string;
  error?: string;
  created_at: string;
}

export interface Stats {
  total_jobs: number;
  jobs_by_status: Record<string, number>;
  jobs_by_portal: Record<string, number>;
  jobs_with_hr_email: number;
  cover_letters_generated: number;
  emails_sent: number;
  emails_delivered: number;
  emails_opened: number;
  emails_clicked: number;
  emails_bounced: number;
  emails_soft_bounced: number;
  jobs_ready: number;
  jobs_missing_hr: number;
  jobs_pending_approval: number;
}

export interface SearchResponse {
  task_id: string;
  celery_task_ids: string[];
  message: string;
  portals: string[];
  estimated_jobs: number;
}

export interface TimelineEvent {
  event: string;
  label: string;
  timestamp?: string | null;
  done: boolean;
  metadata?: Record<string, unknown> | null;
}

export interface JobTimeline {
  job_id: string;
  events: TimelineEvent[];
}

// App State Types
export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface JobsState {
  jobs: Job[];
  totalCount: number;
  loading: boolean;
  filters: JobFilters;
  selected: Set<string>;
  page: number;
}

export interface JobFilters {
  search: string;
  status: string;
  portal: string;
  job_type: string;
  has_hr_email: '' | 'yes' | 'no';
  has_cover: '' | 'yes' | 'no';
  min_score: number;
  max_score?: number;
  scraped_after: string;
  posted_after: string;
  sort_by: 'scraped_at' | 'relevance_score' | 'company' | 'job_title';
  sort_dir: 'asc' | 'desc';
  page: number;
  page_size: number;
}

export interface CandidatesState {
  candidates: Candidate[];
  activeCandidateId: string;
  loading: boolean;
}

export interface NotificationsState {
  pushToken: string | null;
  notifications: any[];
  preferences: NotificationPreferences;
}

export interface NotificationPreferences {
  newJobs: boolean;
  emailUpdates: boolean;
  taskCompletions: boolean;
}

export interface UIState {
  theme: 'light' | 'dark' | 'system';
  sidebarCollapsed: boolean;
  activeTab: string;
}

// API Request/Response Types
export interface ApiResponse<T = any> {
  data?: T;
  error?: string;
  message?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  user: User;
}

export interface RegisterRequest {
  tenant_name: string;
  email: string;
  password: string;
}

export interface BulkSendRequest {
  candidate_id: string;
  job_ids: string[];
  dry_run?: boolean;
  attach_resume?: boolean;
}

export interface BulkSendResponse {
  queued: number;
  skipped: SkippedJob[];
  task_ids: string[];
  dry_run: boolean;
}

export interface SkippedJob {
  job_id: string;
  reason: 'not_found' | 'no_hr_email' | 'no_cover_letter' | 'already_sent';
}

// Error Types
export interface ApiError {
  message: string;
  detail?: string;
  status?: number;
  code?: string;
}

export interface ErrorResponse {
  error?: ApiError;
  detail?: string;
  message?: string;
}

// Tenant / Organization
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

export interface TenantUsage {
  tenant_id: string;
  plan: string;
  usage: Record<string, number | string>;
}

// Blacklist
export interface BlacklistedCompany {
  id: string;
  name: string;
  reason?: string;
  created_at: string;
}

// Billing
export interface Plan {
  name: string;
  price: number;
  features: Record<string, string | number | boolean>;
}

export interface Subscription {
  tenant_id: string;
  plan: string;
  subscription?: {
    id: string;
    status: string;
    provider: string;
    current_period_end: string;
  };
}

export interface CheckoutResponse {
  payment_link?: string;
  order_id?: string;
  [key: string]: unknown;
}

// Direct Send
export interface DirectSendResult {
  sent: number;
  failed: Array<{ email: string; reason: string }>;
  skipped: string[];
}

// Admin
export interface SystemHealth {
  database: 'connected' | 'error' | 'unknown';
  rabbitmq: 'connected' | 'error' | 'unknown';
  redis: 'connected' | 'error' | 'unknown';
  ollama: 'connected' | 'error' | 'not_configured' | 'unknown';
  [key: string]: string;
}

export interface Queue {
  name: string;
  messages: number;
  ready: number;
  unacked: number;
  consumers: number;
  rate?: number;
}

export interface FeatureFlags {
  auto_send_enabled: boolean;
  langchain_enabled: boolean;
  semantic_filter_enabled: boolean;
  score_threshold: number;
}

export interface Portal {
  name: string;
  enabled: boolean;
}

export interface WorkerConfig {
  [worker: string]: {
    scale: number;
    concurrency: number;
  };
}

export interface CronStatus {
  task_name: string;
  circuit_state: string;
  lock_held: boolean;
  runs_per_hour: number;
  failures: number;
}

export interface CronRunSummary {
  id: string;
  task_name: string;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  status: 'running' | 'success' | 'failure' | 'timeout' | 'skipped';
  error_summary: string | null;
  triggered_by: string;
  worker_host: string | null;
  post_state: Record<string, unknown> | null;
  steps_count: number;
}

export interface CronRunDetail extends CronRunSummary {
  error_traceback: string | null;
  pre_state: Record<string, unknown> | null;
  steps: Array<{
    label: string;
    started_at: string;
    ended_at: string;
    ok: boolean;
  }>;
}

// HR Email Pipeline stats (from /stats/hr-email-pipeline)
export interface HrEmailPipelineStats {
  jobs_pending_discovery: number;
  jobs_unreachable: number;
  jobs_found: number;
  cover_ready_missing_hr: number;
  cover_ready_with_hr: number;
  discovery_status_counts?: Record<string, number>;
  missing_hr_by_portal?: Record<string, number>;
}

// Admin Quota
export interface QuotaEntry {
  used: number;
  limit: number;
  resets_at?: string;
  unit?: string;
}

export interface AdminQuota {
  groq?: QuotaEntry;
  hr_email_providers?: Record<string, QuotaEntry>;
  [key: string]: QuotaEntry | Record<string, QuotaEntry> | undefined;
}
