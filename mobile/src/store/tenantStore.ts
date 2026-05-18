import { create } from 'zustand';
import { Tenant } from '../types';
import apiService from '../services/api';

interface TenantStore {
  tenant: Tenant | null;
  loading: boolean;
  error: string | null;
  fetchTenant: () => Promise<void>;
  updateTenant: (data: {
    name?: string;
    requires_approval?: boolean;
    auto_send?: boolean;
    score_threshold?: number;
  }) => Promise<void>;
}

export const useTenantStore = create<TenantStore>((set) => ({
  tenant: null,
  loading: false,
  error: null,

  fetchTenant: async () => {
    set({ loading: true, error: null });
    try {
      const tenant = await apiService.getMyTenant();
      set({ tenant, loading: false });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.detail || 'Failed to load tenant' });
    }
  },

  updateTenant: async (data) => {
    set({ loading: true, error: null });
    try {
      const tenant = await apiService.updateMyTenant(data);
      set({ tenant, loading: false });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.detail || 'Failed to update tenant' });
      throw error;
    }
  },
}));
