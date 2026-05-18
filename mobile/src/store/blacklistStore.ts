import { create } from 'zustand';
import { BlacklistedCompany } from '../types';
import apiService from '../services/api';

interface BlacklistStore {
  items: BlacklistedCompany[];
  loading: boolean;
  error: string | null;
  fetchBlacklist: () => Promise<void>;
  addToBlacklist: (name: string, reason?: string) => Promise<void>;
  updateEntry: (id: string, reason: string) => Promise<void>;
  removeEntry: (id: string) => Promise<void>;
}

export const useBlacklistStore = create<BlacklistStore>((set, get) => ({
  items: [],
  loading: false,
  error: null,

  fetchBlacklist: async () => {
    set({ loading: true, error: null });
    try {
      const items = await apiService.getBlacklist();
      set({ items, loading: false });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.detail || 'Failed to load blacklist' });
    }
  },

  addToBlacklist: async (name: string, reason?: string) => {
    const item = await apiService.addToBlacklist(name, reason);
    set((state) => ({ items: [item, ...state.items] }));
  },

  updateEntry: async (id: string, reason: string) => {
    const updated = await apiService.updateBlacklist(id, reason);
    set((state) => ({
      items: state.items.map((item) => (item.id === id ? updated : item)),
    }));
  },

  removeEntry: async (id: string) => {
    await apiService.removeFromBlacklist(id);
    set((state) => ({ items: state.items.filter((item) => item.id !== id) }));
  },
}));
