import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import axios, { AxiosInstance, AxiosRequestConfig, AxiosError } from 'axios';
import {
  AdminQuota,
  BlacklistedCompany,
  BulkSendRequest,
  BulkSendResponse,
  Candidate,
  CheckoutResponse,
  CronRunDetail,
  CronRunSummary,
  CronStatus,
  DirectSendResult,
  FeatureFlags,
  HrEmailPipelineStats,
  Job,
  JobFilters,
  JobTimeline,
  LoginRequest,
  LoginResponse,
  Plan,
  Portal,
  Queue,
  RegisterRequest,
  SearchResponse,
  SearchTask,
  SendLog,
  Stats,
  Subscription,
  SystemHealth,
  Tenant,
  TenantUsage,
  User,
  WorkerConfig,
} from '../types';
import { logger } from '../utils/logger';

type TokenResponse = {
  access_token: string;
  refresh_token?: string;
  token_type: string;
};

type JobQueryParams = Partial<
  Pick<
    JobFilters,
    | 'search'
    | 'status'
    | 'portal'
    | 'job_type'
    | 'sort_by'
    | 'sort_dir'
    | 'page'
    | 'page_size'
    | 'scraped_after'
  >
> & {
  has_hr_email?: boolean;
  has_cover?: boolean;
  min_score?: number;
  max_score?: number;
  has_active_send?: boolean;
};

const ACCESS_TOKEN_KEY = 'jh_mobile_access_token';
const REFRESH_TOKEN_KEY = 'jh_mobile_refresh_token';
const USER_KEY = 'jh_mobile_user';

const memoryStorage: Record<string, string> = {};

const tokenStorage = {
  async getItem(key: string): Promise<string | null> {
    try {
      if (Platform.OS !== 'web') {
        const value = await SecureStore.getItemAsync(key);
        if (value) return value;
      }
      return (await AsyncStorage.getItem(key)) ?? memoryStorage[key] ?? null;
    } catch {
      return memoryStorage[key] ?? null;
    }
  },

  async setItem(key: string, value: string): Promise<void> {
    memoryStorage[key] = value;
    try {
      if (Platform.OS !== 'web') {
        await SecureStore.setItemAsync(key, value);
      }
      await AsyncStorage.setItem(key, value);
    } catch {
      // Keep the in-memory fallback so the current session still works.
    }
  },

  async removeItem(key: string): Promise<void> {
    delete memoryStorage[key];
    try {
      if (Platform.OS !== 'web') {
        await SecureStore.deleteItemAsync(key);
      }
      await AsyncStorage.removeItem(key);
    } catch {
      // Already cleared from memory.
    }
  },
};

function resolveApiBaseUrl(): string {
  const envBase = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (envBase) return envBase;
  if (__DEV__) return Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';
  return 'https://your-production-api.com';
}

export const API_BASE_URL = resolveApiBaseUrl();

class ApiService {
  private client: AxiosInstance;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private refreshPromise: Promise<string | null> | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    logger.info('API Service initialized', { baseUrl: API_BASE_URL });

    this.client.interceptors.request.use(
      async (config) => {
        if (!this.accessToken) {
          this.accessToken = await tokenStorage.getItem(ACCESS_TOKEN_KEY);
        }
        if (this.accessToken) {
          config.headers.Authorization = `Bearer ${this.accessToken}`;
        }
        // Tag request start time for duration logging
        (config as any)._startTime = Date.now();
        logger.debug('API Request', { method: config.method?.toUpperCase(), url: config.url });
        return config;
      },
      (error) => {
        logger.error('API Request error', { error: error.message });
        return Promise.reject(error);
      }
    );

    this.client.interceptors.response.use(
      (response) => {
        const duration = (response.config as any)._startTime
          ? Date.now() - (response.config as any)._startTime
          : undefined;
        logger.debug('API Response', {
          status: response.status,
          url: response.config.url,
          method: response.config.method?.toUpperCase(),
          duration_ms: duration,
        });
        return response;
      },
      async (error: AxiosError) => {
        const original = error.config as (AxiosRequestConfig & { _retry?: boolean; _startTime?: number }) | undefined;
        const duration = original?._startTime ? Date.now() - original._startTime : undefined;

        logger.warn('API Response error', {
          status: error.response?.status,
          url: original?.url,
          method: (original as any)?.method?.toUpperCase(),
          duration_ms: duration,
          message: error.message,
        });

        if (error.response?.status !== 401 || !original || original._retry) {
          return Promise.reject(error);
        }

        original._retry = true;
        logger.info('Attempting token refresh');
        const nextAccessToken = await this.refreshAccessToken();
        if (!nextAccessToken) {
          logger.warn('Token refresh failed, clearing auth');
          await this.clearAuth();
          return Promise.reject(error);
        }

        original.headers = {
          ...(original.headers ?? {}),
          Authorization: `Bearer ${nextAccessToken}`,
        };
        return this.client(original);
      }
    );
  }

  getBaseUrl(): string {
    return API_BASE_URL;
  }

  async getStoredUser(): Promise<User | null> {
    const raw = await tokenStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as User;
    } catch {
      return null;
    }
  }

  async getStoredAccessToken(): Promise<string | null> {
    if (!this.accessToken) {
      this.accessToken = await tokenStorage.getItem(ACCESS_TOKEN_KEY);
    }
    return this.accessToken;
  }

  private async persistAuth(tokens: TokenResponse, user?: User): Promise<User | undefined> {
    this.accessToken = tokens.access_token;
    this.refreshToken = tokens.refresh_token ?? null;
    await tokenStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
    if (tokens.refresh_token) {
      await tokenStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
    }
    if (user) {
      await tokenStorage.setItem(USER_KEY, JSON.stringify(user));
    }
    return user;
  }

  private async clearAuth(): Promise<void> {
    this.accessToken = null;
    this.refreshToken = null;
    await Promise.all([
      tokenStorage.removeItem(ACCESS_TOKEN_KEY),
      tokenStorage.removeItem(REFRESH_TOKEN_KEY),
      tokenStorage.removeItem(USER_KEY),
    ]);
  }

  private async refreshAccessToken(): Promise<string | null> {
    if (this.refreshPromise) return this.refreshPromise;

    this.refreshPromise = (async () => {
      const refresh = this.refreshToken ?? (await tokenStorage.getItem(REFRESH_TOKEN_KEY));
      if (!refresh) return null;

      try {
        const response = await axios.post<TokenResponse>(`${API_BASE_URL}/auth/refresh`, {
          refresh_token: refresh,
        });
        await this.persistAuth(response.data);
        return response.data.access_token;
      } catch {
        return null;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  async login(credentials: LoginRequest): Promise<LoginResponse> {
    logger.info('Login attempt', { email: credentials.email });
    try {
      const response = await this.client.post<TokenResponse>('/auth/login', credentials);
      await this.persistAuth(response.data);
      const user = await this.getCurrentUser();
      await tokenStorage.setItem(USER_KEY, JSON.stringify(user));

      logger.info('Login successful', { userId: user.id, email: user.email });
      return {
        ...response.data,
        user,
      };
    } catch (error) {
      await this.clearAuth();
      logger.error('Login failed', { email: credentials.email }, error as Error);
      throw error;
    }
  }

  async register(body: RegisterRequest): Promise<LoginResponse> {
    logger.info('Registration attempt', { email: body.email, tenantName: body.tenant_name });
    try {
      const response = await this.client.post<TokenResponse>('/auth/register', body);
      await this.persistAuth(response.data);
      const user = await this.getCurrentUser();
      await tokenStorage.setItem(USER_KEY, JSON.stringify(user));

      logger.info('Registration successful', { userId: user.id, email: user.email });
      return {
        ...response.data,
        user,
      };
    } catch (error) {
      await this.clearAuth();
      logger.error('Registration failed', { email: body.email }, error as Error);
      throw error;
    }
  }

  async logout(): Promise<void> {
    logger.info('Logout attempt');
    const refresh = this.refreshToken ?? (await tokenStorage.getItem(REFRESH_TOKEN_KEY));
    try {
      if (refresh && this.accessToken) {
        await this.client.post('/auth/logout', { refresh_token: refresh }).catch(() => undefined);
      }
      logger.info('Logout successful');
    } catch (error) {
      logger.error('Logout failed', {}, error as Error);
    } finally {
      await this.clearAuth();
    }
  }

  async getCurrentUser(): Promise<User> {
    const response = await this.client.get<User>('/users/me');
    await tokenStorage.setItem(USER_KEY, JSON.stringify(response.data));
    return response.data;
  }

  async getCandidates(): Promise<Candidate[]> {
    const response = await this.client.get<Candidate[]>('/candidates');
    return response.data;
  }

  async getCandidate(id: string): Promise<Candidate> {
    const response = await this.client.get<Candidate>(`/candidates/${id}`);
    return response.data;
  }

  async createCandidate(candidate: Partial<Candidate>): Promise<Candidate> {
    const response = await this.client.post<Candidate>('/candidates', candidate);
    return response.data;
  }

  async updateCandidate(id: string, updates: Partial<Candidate>): Promise<Candidate> {
    const response = await this.client.put<Candidate>(`/candidates/${id}`, updates);
    return response.data;
  }

  async getJobs(params?: JobQueryParams): Promise<{ data: Job[]; count: number }> {
    const [jobsResponse, countResponse] = await Promise.all([
      this.client.get<Job[]>('/jobs', { params }),
      this.client.get<{ count: number }>('/jobs/count', { params: stripPagingParams(params) }),
    ]);

    return {
      data: jobsResponse.data,
      count: countResponse.data.count,
    };
  }

  async getJobIds(params?: JobQueryParams): Promise<string[]> {
    const response = await this.client.get<string[]>('/jobs/ids', { params: stripPagingParams(params) });
    return response.data;
  }

  async getJob(id: string): Promise<Job> {
    const response = await this.client.get<Job>(`/jobs/${id}`);
    return response.data;
  }

  async updateJobStatus(id: string, status: string): Promise<Job> {
    const response = await this.client.patch<Job>(`/jobs/${id}/status`, { status });
    return response.data;
  }

  async generateCoverLetter(
    jobId: string,
    candidateId: string,
    tone = 'professional',
    customInstructions = ''
  ): Promise<{ message: string; celery_task_id: string; job_id: string }> {
    const response = await this.client.post(`/jobs/${jobId}/generate_cover`, {
      candidate_id: candidateId,
      tone,
      custom_instructions: customInstructions,
    });
    return response.data;
  }

  async bulkGenerateCovers(
    jobIds: string[],
    candidateId: string,
    tone = 'professional',
    customInstructions = ''
  ): Promise<{ queued: number; not_found: string[]; task_ids: string[] }> {
    const response = await this.client.post('/jobs/bulk_generate_cover', {
      job_ids: jobIds,
      candidate_id: candidateId,
      tone,
      custom_instructions: customInstructions,
    });
    return response.data;
  }

  async bulkSend(request: BulkSendRequest): Promise<BulkSendResponse> {
    const response = await this.client.post<BulkSendResponse>('/jobs/bulk_send', request);
    return response.data;
  }

  async sendApplication(
    jobId: string,
    request: Omit<BulkSendRequest, 'job_ids'>
  ): Promise<{ message?: string; celery_task_id?: string; job_id?: string; dry_run?: boolean }> {
    const response = await this.client.post(`/jobs/${jobId}/send`, request);
    return response.data;
  }

  async getJobTimeline(jobId: string): Promise<JobTimeline> {
    const response = await this.client.get<JobTimeline>(`/jobs/${jobId}/timeline`);
    return response.data;
  }

  async getSendLogs(params?: {
    job_id?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<SendLog[]> {
    const response = await this.client.get<SendLog[]>('/jobs/send_logs', { params });
    return response.data;
  }

  async getSearchTasks(limit = 10): Promise<SearchTask[]> {
    const response = await this.client.get<SearchTask[]>('/search/tasks', {
      params: { limit },
    });
    return response.data;
  }

  async getSearchTask(id: string): Promise<SearchTask> {
    const response = await this.client.get<SearchTask>(`/search/tasks/${id}`);
    return response.data;
  }

  async triggerSearch(params: {
    job_titles: string[];
    locations: string[];
    portals: string[];
    candidate_id: string;
    max_results_per_portal?: number;
    auto_generate_covers?: boolean;
  }): Promise<SearchResponse> {
    const response = await this.client.post<SearchResponse>('/search', {
      ...params,
      max_results_per_portal: params.max_results_per_portal ?? 50,
      auto_generate_covers: params.auto_generate_covers ?? false,
    });
    return response.data;
  }

  async getStats(params?: { candidate_id?: string }): Promise<Stats> {
    const response = await this.client.get<Stats>('/stats', { params });
    return response.data;
  }

  async healthCheck(): Promise<{ status: string; version?: string; environment?: string }> {
    const response = await this.client.get<{ status: string; version?: string; environment?: string }>('/health');
    return response.data;
  }

  // ── Auth extras ──────────────────────────────────────────────────────────

  async forgotPassword(email: string): Promise<void> {
    await this.client.post('/auth/forgot-password', { email });
  }

  async resetPassword(token: string, newPassword: string): Promise<void> {
    await this.client.post('/auth/reset-password', { token, new_password: newPassword });
  }

  // ── Users / Team ──────────────────────────────────────────────────────────

  async updateProfile(data: { email?: string; current_password?: string; new_password?: string }): Promise<User> {
    const response = await this.client.put<User>('/users/me', data);
    await tokenStorage.setItem(USER_KEY, JSON.stringify(response.data));
    return response.data;
  }

  async listUsers(): Promise<User[]> {
    const response = await this.client.get<User[]>('/users');
    return response.data;
  }

  async inviteUser(email: string, role: string): Promise<User> {
    const response = await this.client.post<User>('/users/invite', { email, role });
    return response.data;
  }

  async removeUser(userId: string): Promise<void> {
    await this.client.delete(`/users/${userId}`);
  }

  async changeUserRole(userId: string, role: string): Promise<User> {
    const response = await this.client.patch<User>(`/users/${userId}/role`, { role });
    return response.data;
  }

  // ── Candidates extras ─────────────────────────────────────────────────────

  async uploadResume(candidateId: string, fileUri: string, fileName: string): Promise<Candidate> {
    const formData = new FormData();
    formData.append('file', {
      uri: fileUri,
      name: fileName,
      type: 'application/pdf',
    } as any);
    const response = await this.client.post<Candidate>(`/candidates/${candidateId}/resume`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  getResumeDownloadUrl(candidateId: string): string {
    return `${API_BASE_URL}/candidates/${candidateId}/resume`;
  }

  async directHRSend(candidateId: string, hrEmails: string[]): Promise<DirectSendResult> {
    const response = await this.client.post<DirectSendResult>('/direct-send', {
      candidate_id: candidateId,
      hr_emails: hrEmails,
    });
    return response.data;
  }

  // ── Jobs extras ───────────────────────────────────────────────────────────

  async setJobHrEmail(jobId: string, hrEmail: string): Promise<Job> {
    const response = await this.client.patch<Job>(`/jobs/${jobId}/hr-email`, { hr_email: hrEmail });
    return response.data;
  }

  // ── Stats extras ──────────────────────────────────────────────────────────

  async getHrEmailPipeline(): Promise<HrEmailPipelineStats> {
    const response = await this.client.get<HrEmailPipelineStats>('/stats/hr-email-pipeline');
    return response.data;
  }

  // ── Blacklist ─────────────────────────────────────────────────────────────

  async getBlacklist(): Promise<BlacklistedCompany[]> {
    const response = await this.client.get<BlacklistedCompany[]>('/blacklist');
    return response.data;
  }

  async addToBlacklist(name: string, reason?: string): Promise<BlacklistedCompany> {
    const response = await this.client.post<BlacklistedCompany>('/blacklist', { name, reason });
    return response.data;
  }

  async updateBlacklist(id: string, reason: string): Promise<BlacklistedCompany> {
    const response = await this.client.put<BlacklistedCompany>(`/blacklist/${id}`, { reason });
    return response.data;
  }

  async removeFromBlacklist(id: string): Promise<void> {
    await this.client.delete(`/blacklist/${id}`);
  }

  // ── Tenant ────────────────────────────────────────────────────────────────

  async getMyTenant(): Promise<Tenant> {
    const response = await this.client.get<Tenant>('/tenants/me');
    return response.data;
  }

  async updateMyTenant(data: {
    name?: string;
    requires_approval?: boolean;
    auto_send?: boolean;
    score_threshold?: number;
  }): Promise<Tenant> {
    const response = await this.client.put<Tenant>('/tenants/me', data);
    return response.data;
  }

  async getTenantUsage(): Promise<TenantUsage> {
    const response = await this.client.get<TenantUsage>('/tenants/me/usage');
    return response.data;
  }

  // ── Billing ───────────────────────────────────────────────────────────────

  async getPlans(): Promise<Plan[]> {
    const response = await this.client.get<Plan[]>('/billing/plans');
    return response.data;
  }

  async getSubscription(): Promise<Subscription> {
    const response = await this.client.get<Subscription>('/billing/subscription');
    return response.data;
  }

  async createCheckout(plan: string): Promise<CheckoutResponse> {
    const response = await this.client.post<CheckoutResponse>('/billing/create-checkout', null, {
      params: { plan },
    });
    return response.data;
  }

  async cancelSubscription(): Promise<void> {
    await this.client.post('/billing/cancel');
  }

  // ── Admin ─────────────────────────────────────────────────────────────────

  async getSystemHealth(): Promise<SystemHealth> {
    const response = await this.client.get<SystemHealth>('/admin/system/health');
    return response.data;
  }

  async getQueues(): Promise<Queue[]> {
    const response = await this.client.get<Queue[]>('/admin/queues');
    return response.data;
  }

  async getAdminLogs(level: string, lines = 100): Promise<string[]> {
    const response = await this.client.get<string[]>(`/admin/logs/${level}`, { params: { lines } });
    return response.data;
  }

  async getFeatureFlags(): Promise<FeatureFlags> {
    const response = await this.client.get<FeatureFlags>('/admin/features');
    return response.data;
  }

  async updateFeatureFlags(flags: Partial<FeatureFlags>): Promise<FeatureFlags> {
    const response = await this.client.put<FeatureFlags>('/admin/features', flags);
    return response.data;
  }

  async getPortals(): Promise<Portal[]> {
    const response = await this.client.get<Portal[]>('/admin/portals');
    return response.data;
  }

  async togglePortal(portal: string, enabled: boolean): Promise<void> {
    await this.client.put(`/admin/portals/${portal}/toggle`, null, { params: { enabled } });
  }

  async getWorkerConfig(): Promise<WorkerConfig> {
    const response = await this.client.get<WorkerConfig>('/admin/workers/config');
    return response.data;
  }

  async updateWorkerScale(worker: string, scale?: number, concurrency?: number): Promise<void> {
    await this.client.put('/admin/workers/scale', { worker, scale, concurrency });
  }

  async applyPerformanceMode(mode: 'turbo' | 'normal' | 'economy'): Promise<void> {
    await this.client.post('/admin/workers/performance-mode', { mode });
  }

  async getCronStatus(): Promise<CronStatus[]> {
    const response = await this.client.get<CronStatus[]>('/admin/cron/status');
    return response.data;
  }

  async resetCronCircuit(taskName: string): Promise<void> {
    await this.client.post(`/admin/cron/${taskName}/reset_circuit`);
  }

  async releaseCronLock(taskName: string): Promise<void> {
    await this.client.post(`/admin/cron/${taskName}/release_lock`);
  }

  async triggerQuickAction(action: string): Promise<{ action: string; task_id: string; status: string }> {
    const response = await this.client.post<{ action: string; task_id: string; status: string }>(
      `/admin/quick-actions/${action}`
    );
    return response.data;
  }

  async getCronRuns(params?: { task?: string; status?: string; limit?: number; offset?: number }): Promise<CronRunSummary[]> {
    const response = await this.client.get<CronRunSummary[]>('/admin/cron/runs', { params });
    return response.data;
  }

  async getCronRun(runId: string): Promise<CronRunDetail> {
    const response = await this.client.get<CronRunDetail>(`/admin/cron/runs/${runId}`);
    return response.data;
  }

  async getAdminQuota(): Promise<AdminQuota> {
    const response = await this.client.get<AdminQuota>('/admin/quota');
    return response.data;
  }
}

function stripPagingParams(params?: JobQueryParams): JobQueryParams | undefined {
  if (!params) return undefined;
  const { page: _page, page_size: _pageSize, sort_by: _sortBy, sort_dir: _sortDir, ...rest } = params;
  return rest;
}

export const apiService = new ApiService();
export default apiService;
