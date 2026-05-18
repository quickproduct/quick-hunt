import { create } from 'zustand';
import { CronStatus, FeatureFlags, Portal, Queue, SystemHealth, WorkerConfig } from '../types';
import apiService from '../services/api';

interface AdminStore {
  health: SystemHealth | null;
  queues: Queue[];
  featureFlags: FeatureFlags | null;
  portals: Portal[];
  workerConfig: WorkerConfig | null;
  cronStatus: CronStatus[];
  loading: boolean;
  error: string | null;
  fetchHealth: () => Promise<void>;
  fetchQueues: () => Promise<void>;
  fetchFeatureFlags: () => Promise<void>;
  updateFeatureFlags: (flags: Partial<FeatureFlags>) => Promise<void>;
  fetchPortals: () => Promise<void>;
  togglePortal: (portal: string, enabled: boolean) => Promise<void>;
  fetchWorkerConfig: () => Promise<void>;
  updateWorkerScale: (worker: string, scale?: number, concurrency?: number) => Promise<void>;
  applyPerformanceMode: (mode: 'turbo' | 'normal' | 'economy') => Promise<void>;
  fetchCronStatus: () => Promise<void>;
  resetCronCircuit: (taskName: string) => Promise<void>;
  releaseCronLock: (taskName: string) => Promise<void>;
  triggerQuickAction: (action: string) => Promise<string>;
}

export const useAdminStore = create<AdminStore>((set, get) => ({
  health: null,
  queues: [],
  featureFlags: null,
  portals: [],
  workerConfig: null,
  cronStatus: [],
  loading: false,
  error: null,

  fetchHealth: async () => {
    const health = await apiService.getSystemHealth();
    set({ health });
  },

  fetchQueues: async () => {
    const queues = await apiService.getQueues();
    set({ queues });
  },

  fetchFeatureFlags: async () => {
    const featureFlags = await apiService.getFeatureFlags();
    set({ featureFlags });
  },

  updateFeatureFlags: async (flags) => {
    const featureFlags = await apiService.updateFeatureFlags(flags);
    set({ featureFlags });
  },

  fetchPortals: async () => {
    const portals = await apiService.getPortals();
    set({ portals });
  },

  togglePortal: async (portal: string, enabled: boolean) => {
    await apiService.togglePortal(portal, enabled);
    set((state) => ({
      portals: state.portals.map((p) => (p.name === portal ? { ...p, enabled } : p)),
    }));
  },

  fetchWorkerConfig: async () => {
    const workerConfig = await apiService.getWorkerConfig();
    set({ workerConfig });
  },

  updateWorkerScale: async (worker, scale, concurrency) => {
    await apiService.updateWorkerScale(worker, scale, concurrency);
    await get().fetchWorkerConfig();
  },

  applyPerformanceMode: async (mode) => {
    await apiService.applyPerformanceMode(mode);
  },

  fetchCronStatus: async () => {
    const cronStatus = await apiService.getCronStatus();
    set({ cronStatus });
  },

  resetCronCircuit: async (taskName) => {
    await apiService.resetCronCircuit(taskName);
    await get().fetchCronStatus();
  },

  releaseCronLock: async (taskName) => {
    await apiService.releaseCronLock(taskName);
    await get().fetchCronStatus();
  },

  triggerQuickAction: async (action) => {
    const result = await apiService.triggerQuickAction(action);
    return result.task_id;
  },
}));
