'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import toast from 'react-hot-toast';
// Admin API imports temporarily stubbed
// TODO: Add admin endpoints to backend and restore these imports
const getAdminSummary = async () => ({ health: {}, queues: [], features: {}, portals: [], worker_config: {}, cron_status: {}, performance_mode: 'normal', live_status: {}, paused_services: [], scrape_filter: {} });
const getFeatureFlags = async () => ({ auto_send_enabled: false, langchain_enabled: false, semantic_filter_enabled: false, score_threshold: 0.5 });
const apiUpdateFeatures = async (_data: any) => ({}) as any;
const getPortals = async () => [];
const apiTogglePortal = async (_name: string, _enabled: boolean) => ({}) as any;
const getWorkerConfig = async () => ({ workers: {} });
const apiUpdateScale = async (_data: any) => ({}) as any;
const apiApplyPerfMode = async (_mode: string) => ({}) as any;
const getPerformanceMode = async () => ({ mode: 'normal' });
const getCronStatus = async () => ({});
const apiResetCircuit = async (_taskName: string) => ({}) as any;
const apiReleaseLock = async (_taskName: string) => ({}) as any;
const apiQuickAction = async (_action: string) => ({}) as any;
const getWorkersLiveStatus = async () => ({ services: {} });
const apiRestartWorkers = async (_service?: string) => ({}) as any;
const apiPauseWorker = async (_service: string) => ({}) as any;
const apiResumeWorker = async (_service: string) => ({}) as any;
const apiRollback = async () => ({}) as any;
const getWorkersPausedState = async () => ({ paused_services: [] });
const apiGetScrapeFilter = async () => ({ max_job_age_days: 30, strict_date_mode: false });
const apiUpdateScrapeFilter = async (_data: any) => ({}) as any;

type SystemHealth = any;
type QueueInfo = any;
type FeatureFlags = any;
type PortalInfo = any;
type WorkerConfig = any;
type CronTaskStatus = any;
type WorkersLiveStatusResponse = any;
type AdminSummary = any;
type ScrapeFilterConfig = any;

interface AdminDataState {
  health: SystemHealth | null;
  queues: QueueInfo[];
  features: FeatureFlags | null;
  portals: PortalInfo[];
  workerConfig: WorkerConfig | null;
  cronStatus: Record<string, CronTaskStatus> | null;
  performanceMode: string;
  liveStatus: WorkersLiveStatusResponse | null;
  pausedServices: string[];
  scrapeFilter: ScrapeFilterConfig | null;
  loading: boolean;
  refreshing: boolean;
  errors: Record<string, string>;
}

export function useAdminData() {
  const [state, setState] = useState<AdminDataState>({
    health: null,
    queues: [],
    features: null,
    portals: [],
    workerConfig: null,
    cronStatus: null,
    performanceMode: 'normal',
    liveStatus: null,
    pausedServices: [],
    scrapeFilter: null,
    loading: true,
    refreshing: false,
    errors: {},
  });

  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  const setError = useCallback((key: string, msg: string) => {
    setState((s) => ({ ...s, errors: { ...s.errors, [key]: msg } }));
  }, []);

  const clearError = useCallback((key: string) => {
    setState((s) => {
      const next = { ...s.errors };
      delete next[key];
      return { ...s, errors: next };
    });
  }, []);

  const fetchCore = useCallback(async (showSpinner = false) => {
    if (showSpinner) setState((s) => ({ ...s, loading: true }));
    setState((s) => ({ ...s, refreshing: true }));

    const results = await Promise.allSettled([
      getAdminSummary(),
      getFeatureFlags(),
      getPortals(),
      getWorkerConfig(),
      getCronStatus(),
      apiGetScrapeFilter(),
    ]);

    if (!mountedRef.current) return;

    const newErrors: Record<string, string> = {};

    if (results[0].status === 'fulfilled') {
      const summary: AdminSummary = results[0].value;
      setState((s) => ({
        ...s,
        health: summary.health,
        queues: summary.queues.items,
        performanceMode: summary.performance_mode?.mode || 'normal',
      }));
      clearError('summary');
    } else {
      newErrors['summary'] = 'Failed to load system status';
    }

    if (results[1].status === 'fulfilled') {
      setState((s) => ({ ...s, features: (results[1] as PromiseFulfilledResult<FeatureFlags>).value }));
    } else {
      newErrors['features'] = 'Failed to load feature flags';
    }

    if (results[2].status === 'fulfilled') {
      setState((s) => ({ ...s, portals: (results[2] as PromiseFulfilledResult<PortalInfo[]>).value }));
    } else {
      newErrors['portals'] = 'Failed to load portals';
    }

    if (results[3].status === 'fulfilled') {
      const wc = (results[3] as PromiseFulfilledResult<WorkerConfig>).value;
      setState((s) => ({ ...s, workerConfig: wc }));
    } else {
      newErrors['workers'] = 'Failed to load worker config';
    }

    if (results[4].status === 'fulfilled') {
      setState((s) => ({ ...s, cronStatus: (results[4] as PromiseFulfilledResult<Record<string, CronTaskStatus>>).value }));
    } else {
      newErrors['cron'] = 'Failed to load cron status';
    }

    if (results[5].status === 'fulfilled') {
      setState((s) => ({ ...s, scrapeFilter: (results[5] as PromiseFulfilledResult<ScrapeFilterConfig>).value }));
    }

    setState((s) => ({
      ...s,
      loading: false,
      refreshing: false,
      errors: { ...s.errors, ...newErrors },
    }));
  }, [clearError]);

  const fetchLiveStatus = useCallback(async () => {
    try {
      const [status, paused] = await Promise.all([
        getWorkersLiveStatus(),
        getWorkersPausedState().catch(() => ({ paused_services: [] })),
      ]);
      if (!mountedRef.current) return;
      setState((s) => ({
        ...s,
        liveStatus: status,
        pausedServices: paused.paused_services,
      }));
    } catch {
      // silently ignore
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchCore(true);
    fetchLiveStatus();
    const coreInterval = setInterval(() => fetchCore(false), 30000);
    const liveInterval = setInterval(fetchLiveStatus, 10000);
    return () => {
      mountedRef.current = false;
      clearInterval(coreInterval);
      clearInterval(liveInterval);
    };
  }, [fetchCore, fetchLiveStatus]);

  const handleRefresh = useCallback(() => {
    fetchCore(false);
    fetchLiveStatus();
  }, [fetchCore, fetchLiveStatus]);

  const updateFeatureToggle = useCallback(async (key: keyof FeatureFlags) => {
    setState((s) => {
      if (!s.features) return s;
      return { ...s, features: { ...s.features, [key]: !s.features[key] } };
    });
    try {
      const current = state.features;
      if (!current) return;
      const newVal = !current[key];
      const updated = await apiUpdateFeatures({ [key]: newVal } as Partial<FeatureFlags>);
      setState((s) => ({ ...s, features: updated }));
      toast.success(`${String(key)} ${newVal ? 'enabled' : 'disabled'}`);
    } catch {
      toast.error('Failed to update feature');
      fetchCore(false);
    }
  }, [state.features, fetchCore]);

  const updateScoreThreshold = useCallback(async (val: number) => {
    setState((s) => {
      if (!s.features) return s;
      return { ...s, features: { ...s.features, score_threshold: val } };
    });
    try {
      const updated = await apiUpdateFeatures({ score_threshold: val });
      setState((s) => ({ ...s, features: updated }));
    } catch {
      toast.error('Failed to update score threshold');
    }
  }, []);

  const handlePortalToggle = useCallback(async (name: string, enabled: boolean) => {
    setState((s) => ({
      ...s,
      portals: s.portals.map((p) => p.name === name ? { ...p, enabled: !enabled } : p),
    }));
    try {
      await apiTogglePortal(name, !enabled);
      toast.success(`${name} ${!enabled ? 'enabled' : 'disabled'}`);
    } catch {
      toast.error('Failed to toggle portal');
      fetchCore(false);
    }
  }, [fetchCore]);

  const handlePerformanceMode = useCallback(async (mode: string, setLoading?: (k: string, v: boolean) => void) => {
    setLoading?.('perf_mode', true);
    try {
      const result = await apiApplyPerfMode(mode);
      setState((s) => ({ ...s, performanceMode: mode }));
      if (result?.concurrency_applied_live && !result?.restart_required) {
        toast.success(`${mode} mode applied live — concurrency updated`);
      } else if (result?.restart_required) {
        toast.success(`${mode} mode saved — run docker compose up -d to scale replicas`, { duration: 6000 });
      } else {
        toast.success(`Performance mode set to ${mode}`);
      }
      setTimeout(() => { fetchCore(false); fetchLiveStatus(); }, 2000);
    } catch {
      toast.error('Failed to apply performance mode');
    } finally {
      setLoading?.('perf_mode', false);
    }
  }, [fetchCore, fetchLiveStatus]);

  const handleWorkerScale = useCallback(async (worker: string, scale: number, concurrency: number, setLoading?: (k: string, v: boolean) => void) => {
    setLoading?.(`scale_${worker}`, true);
    try {
      const result = await apiUpdateScale({ worker, scale, concurrency });
      if (result?.concurrency_applied_live && !result?.restart_required) {
        toast.success(`${worker} concurrency updated live`);
      } else if (result?.restart_required) {
        toast.success(`${worker} config saved — restart containers to apply scale change`, { duration: 5000 });
      } else {
        toast.success(`${worker} workers updated`);
      }
      setTimeout(() => fetchLiveStatus(), 2000);
    } catch {
      toast.error('Failed to update worker scale');
      fetchCore(false);
    } finally {
      setLoading?.(`scale_${worker}`, false);
    }
  }, [fetchCore, fetchLiveStatus]);

  const handleRestartWorker = useCallback(async (service: string) => {
    try {
      const result = await apiRestartWorkers(service);
      if (result.restarted) toast.success(`${service} pool restarted`);
      else toast.error(result.error || 'Restart failed');
      setTimeout(() => fetchLiveStatus(), 3000);
    } catch {
      toast.error('Failed to restart worker');
    }
  }, [fetchLiveStatus]);

  const handleRestartAll = useCallback(async () => {
    try {
      const result = await apiRestartWorkers();
      if (result.restarted) toast.success('All worker pools restarted');
      else toast.error(result.error || 'Restart failed');
      setTimeout(() => fetchLiveStatus(), 3000);
    } catch {
      toast.error('Failed to restart all workers');
    }
  }, [fetchLiveStatus]);

  const handlePauseWorker = useCallback(async (service: string) => {
    try {
      const result = await apiPauseWorker(service);
      if (result.paused) {
        toast.success(`${service} paused — stopped consuming`);
        setState((s) => ({ ...s, pausedServices: [...s.pausedServices, service] }));
      } else {
        toast.error(result.error || 'Pause failed');
      }
      setTimeout(() => fetchLiveStatus(), 2000);
    } catch {
      toast.error('Failed to pause worker');
    }
  }, [fetchLiveStatus]);

  const handleResumeWorker = useCallback(async (service: string) => {
    try {
      const result = await apiResumeWorker(service);
      if (result.resumed) {
        toast.success(`${service} resumed — consuming again`);
        setState((s) => ({ ...s, pausedServices: s.pausedServices.filter((p) => p !== service) }));
      } else {
        toast.error(result.error || 'Resume failed');
      }
      setTimeout(() => fetchLiveStatus(), 2000);
    } catch {
      toast.error('Failed to resume worker');
    }
  }, [fetchLiveStatus]);

  const handleRollback = useCallback(async () => {
    try {
      await apiRollback();
      toast.success('Config rolled back to previous state');
      setTimeout(() => { fetchCore(true); fetchLiveStatus(); }, 2000);
    } catch {
      toast.error('Rollback failed — snapshot may have expired');
    }
  }, [fetchCore, fetchLiveStatus]);

  const handleCronAction = useCallback(async (taskName: string, action: 'reset_circuit' | 'release_lock') => {
    try {
      if (action === 'reset_circuit') await apiResetCircuit(taskName);
      else await apiReleaseLock(taskName);
      toast.success(`${action} for ${taskName}`);
      setTimeout(() => fetchCore(false), 1000);
    } catch {
      toast.error(`Failed to ${action}`);
    }
  }, [fetchCore]);

  const handleQuickAction = useCallback(async (action: string) => {
    try {
      const result = await apiQuickAction(action);
      if (result.reset !== undefined) {
        toast.success(`Reset ${result.reset} jobs`);
      } else if (result.task_id) {
        toast.success(`Task dispatched: ${result.task_id}`);
      } else if (result.count !== undefined) {
        toast.success(`${action}: ${result.count} jobs affected`);
      }
    } catch {
      toast.error('Failed to trigger action');
    }
  }, []);

  const updateScrapeFilter = useCallback(async (updates: Partial<ScrapeFilterConfig>) => {
    try {
      const result = await apiUpdateScrapeFilter(updates);
      setState((s) => ({
        ...s,
        scrapeFilter: {
          max_job_age_days: result.max_job_age_days,
          strict_date_mode: result.strict_date_mode,
        },
      }));
      toast.success('Scrape filter updated — takes effect on next scrape');
    } catch {
      toast.error('Failed to update scrape filter');
    }
  }, []);

  return {
    ...state,
    handleRefresh,
    updateFeatureToggle,
    updateScoreThreshold,
    handlePortalToggle,
    handlePerformanceMode,
    handleWorkerScale,
    handleRestartWorker,
    handleRestartAll,
    handlePauseWorker,
    handleResumeWorker,
    handleRollback,
    handleCronAction,
    handleQuickAction,
    updateScrapeFilter,
  };
}
