import { create } from 'zustand';
import { SendLog } from '../types';
import apiService from '../services/api';

const PAGE_SIZE = 50;

interface SendLogsStore {
  logs: SendLog[];
  statusFilter: string;
  loading: boolean;
  isFetchingMore: boolean;
  hasMore: boolean;
  currentPage: number;
  error: string | null;
  fetchLogs: (jobId?: string) => Promise<void>;
  loadMore: (jobId?: string) => Promise<void>;
  setStatusFilter: (status: string) => void;
}

export const useSendLogsStore = create<SendLogsStore>((set, get) => ({
  logs: [],
  statusFilter: '',
  loading: false,
  isFetchingMore: false,
  hasMore: false,
  currentPage: 1,
  error: null,

  fetchLogs: async (jobId?: string) => {
    set({ loading: true, error: null, currentPage: 1 });
    try {
      const { statusFilter } = get();
      const logs = await apiService.getSendLogs({
        job_id: jobId,
        status: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset: 0,
      });
      set({ logs, loading: false, hasMore: logs.length === PAGE_SIZE });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.detail || 'Failed to load logs' });
    }
  },

  loadMore: async (jobId?: string) => {
    const { statusFilter, currentPage, hasMore, isFetchingMore, loading } = get();
    if (!hasMore || isFetchingMore || loading) return;

    const nextPage = currentPage + 1;
    set({ isFetchingMore: true });
    try {
      const more = await apiService.getSendLogs({
        job_id: jobId,
        status: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset: (nextPage - 1) * PAGE_SIZE,
      });
      set((state) => ({
        logs: [...state.logs, ...more],
        currentPage: nextPage,
        hasMore: more.length === PAGE_SIZE,
        isFetchingMore: false,
      }));
    } catch {
      set({ isFetchingMore: false });
    }
  },

  setStatusFilter: (status: string) => {
    set({ statusFilter: status, logs: [], currentPage: 1, hasMore: false });
  },
}));
