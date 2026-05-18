import { create } from 'zustand';
import { Job, JobFilters, JobsState, JobStatus } from '../types';
import apiService from '../services/api';
import { logger } from '../utils/logger';

interface JobsStore extends Omit<JobsState, 'page'> {
  error: string | null;
  hasMore: boolean;
  isFetchingMore: boolean;
  currentPage: number;
  fetchJobs: () => Promise<void>;
  loadMore: () => Promise<void>;
  setFilters: (filters: Partial<JobFilters>) => void;
  resetFilters: () => void;
  toggleSelect: (jobId: string) => void;
  selectAllPage: () => void;
  selectAllMatching: () => Promise<void>;
  clearSelection: () => void;
  updateJobStatus: (jobId: string, status: JobStatus) => Promise<void>;
  setHrEmail: (jobId: string, hrEmail: string) => Promise<void>;
  generateCoverLetter: (jobId: string, candidateId: string) => Promise<void>;
  bulkGenerateCovers: (jobIds: string[], candidateId: string) => Promise<number>;
  sendApplication: (jobId: string, candidateId: string) => Promise<void>;
  bulkSendApplications: (jobIds: string[], candidateId: string, dryRun?: boolean) => Promise<number>;
}

export const DEFAULT_FILTERS: JobFilters = {
  search: '',
  status: '',
  portal: '',
  job_type: '',
  has_hr_email: '',
  has_cover: '',
  min_score: 0,
  scraped_after: '',
  posted_after: '',
  sort_by: 'scraped_at',
  sort_dir: 'desc',
  page: 1,
  page_size: 20,
};

function buildApiParams(filters: JobFilters, page: number) {
  const params: Record<string, string | number | boolean> = {
    page,
    page_size: filters.page_size,
    sort_by: filters.sort_by,
    sort_dir: filters.sort_dir,
  };

  if (filters.search) params.search = filters.search;
  if (filters.status) params.status = filters.status;
  if (filters.portal) params.portal = filters.portal;
  if (filters.job_type) params.job_type = filters.job_type;
  if (filters.has_hr_email === 'yes') params.has_hr_email = true;
  if (filters.has_hr_email === 'no') params.has_hr_email = false;
  if (filters.has_cover === 'yes') params.has_cover = true;
  if (filters.has_cover === 'no') params.has_cover = false;
  if (filters.min_score > 0) params.min_score = filters.min_score / 100;
  if (filters.max_score !== undefined) params.max_score = filters.max_score / 100;
  if (filters.scraped_after) params.scraped_after = filters.scraped_after;
  if (filters.posted_after) params.posted_after = filters.posted_after;

  return params;
}

export const useJobsStore = create<JobsStore>((set, get) => ({
  jobs: [],
  totalCount: 0,
  loading: false,
  isFetchingMore: false,
  error: null,
  filters: DEFAULT_FILTERS,
  selected: new Set(),
  currentPage: 1,
  hasMore: false,

  fetchJobs: async () => {
    const { filters } = get();
    set({ loading: true, error: null, currentPage: 1 });

    try {
      logger.info('Fetching jobs', { filters });
      const response = await apiService.getJobs(buildApiParams(filters, 1));
      const hasMore = filters.page_size < response.count;
      set({
        jobs: response.data,
        totalCount: response.count,
        loading: false,
        currentPage: 1,
        hasMore,
      });
      logger.info('Jobs fetched successfully', { count: response.data.length, total: response.count });
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'Failed to load jobs';
      logger.error('Error fetching jobs', { filters, errorMessage }, error);
      set({ jobs: [], totalCount: 0, loading: false, hasMore: false, error: errorMessage });
    }
  },

  loadMore: async () => {
    const { filters, currentPage, hasMore, isFetchingMore, loading } = get();
    if (!hasMore || isFetchingMore || loading) return;

    const nextPage = currentPage + 1;
    set({ isFetchingMore: true });

    try {
      const response = await apiService.getJobs(buildApiParams(filters, nextPage));
      const loadedSoFar = nextPage * filters.page_size;
      set((state) => ({
        jobs: [...state.jobs, ...response.data],
        totalCount: response.count,
        currentPage: nextPage,
        hasMore: loadedSoFar < response.count,
        isFetchingMore: false,
      }));
    } catch (error: any) {
      logger.error('Error loading more jobs', {}, error);
      set({ isFetchingMore: false });
    }
  },

  setFilters: (newFilters: Partial<JobFilters>) => {
    const currentFilters = get().filters;
    set({ filters: { ...currentFilters, ...newFilters } });
  },

  resetFilters: () => {
    set({ filters: DEFAULT_FILTERS, selected: new Set() });
  },

  toggleSelect: (jobId: string) => {
    const newSelected = new Set(get().selected);
    if (newSelected.has(jobId)) newSelected.delete(jobId);
    else newSelected.add(jobId);
    set({ selected: newSelected });
  },

  selectAllPage: () => {
    const { jobs, selected } = get();
    const next = new Set(selected);
    const allSelected = jobs.length > 0 && jobs.every((job) => next.has(job.id));
    if (allSelected) jobs.forEach((job) => next.delete(job.id));
    else jobs.forEach((job) => next.add(job.id));
    set({ selected: next });
  },

  selectAllMatching: async () => {
    const { filters, currentPage } = get();
    const ids = await apiService.getJobIds(buildApiParams(filters, currentPage));
    set({ selected: new Set(ids) });
  },

  clearSelection: () => {
    set({ selected: new Set() });
  },

  updateJobStatus: async (jobId: string, status: JobStatus) => {
    try {
      logger.info('Updating job status', { jobId, status });
      const updatedJob = await apiService.updateJobStatus(jobId, status);
      set((state) => ({
        jobs: state.jobs.map((job) => (job.id === jobId ? updatedJob : job)),
      }));
      logger.info('Job status updated successfully', { jobId, status });
    } catch (error) {
      logger.error('Failed to update job status', { jobId, status }, error as Error);
      throw error;
    }
  },

  generateCoverLetter: async (jobId: string, candidateId: string) => {
    try {
      logger.info('Generating cover letter', { jobId, candidateId });
      await apiService.generateCoverLetter(jobId, candidateId);
      await get().fetchJobs();
      logger.info('Cover letter generation queued', { jobId, candidateId });
    } catch (error) {
      logger.error('Failed to generate cover letter', { jobId, candidateId }, error as Error);
      throw error;
    }
  },

  bulkGenerateCovers: async (jobIds: string[], candidateId: string) => {
    try {
      logger.info('Bulk generating cover letters', { jobCount: jobIds.length, candidateId });
      const result = await apiService.bulkGenerateCovers(jobIds, candidateId);
      await get().fetchJobs();
      logger.info('Bulk cover generation queued', { queued: result.queued });
      return result.queued;
    } catch (error) {
      logger.error('Failed to bulk generate covers', { jobCount: jobIds.length, candidateId }, error as Error);
      throw error;
    }
  },

  sendApplication: async (jobId: string, candidateId: string) => {
    try {
      logger.info('Sending application', { jobId, candidateId });
      await apiService.bulkSend({
        candidate_id: candidateId,
        job_ids: [jobId],
        attach_resume: true,
        dry_run: false,
      });
      await get().fetchJobs();
      logger.info('Application send queued', { jobId, candidateId });
    } catch (error) {
      logger.error('Failed to send application', { jobId, candidateId }, error as Error);
      throw error;
    }
  },

  setHrEmail: async (jobId: string, hrEmail: string) => {
    try {
      const updatedJob = await apiService.setJobHrEmail(jobId, hrEmail);
      set((state) => ({
        jobs: state.jobs.map((job) => (job.id === jobId ? updatedJob : job)),
      }));
    } catch (error) {
      logger.error('Failed to set HR email', { jobId, hrEmail }, error as Error);
      throw error;
    }
  },

  bulkSendApplications: async (jobIds: string[], candidateId: string, dryRun = false) => {
    try {
      logger.info('Bulk sending applications', { jobCount: jobIds.length, candidateId, dryRun });
      const result = await apiService.bulkSend({
        candidate_id: candidateId,
        job_ids: jobIds,
        attach_resume: true,
        dry_run: dryRun,
      });
      await get().fetchJobs();
      logger.info('Bulk application send queued', { queued: result.queued });
      return result.queued;
    } catch (error) {
      logger.error('Failed to bulk send applications', { jobCount: jobIds.length, candidateId }, error as Error);
      throw error;
    }
  },
}));
