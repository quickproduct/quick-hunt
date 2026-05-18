import { create } from 'zustand';
import { Plan, Subscription } from '../types';
import apiService from '../services/api';

interface BillingStore {
  plans: Plan[];
  subscription: Subscription | null;
  loading: boolean;
  error: string | null;
  fetchPlans: () => Promise<void>;
  fetchSubscription: () => Promise<void>;
  createCheckout: (plan: string) => Promise<string | null>;
  cancelSubscription: () => Promise<void>;
}

export const useBillingStore = create<BillingStore>((set) => ({
  plans: [],
  subscription: null,
  loading: false,
  error: null,

  fetchPlans: async () => {
    set({ loading: true, error: null });
    try {
      const plans = await apiService.getPlans();
      set({ plans, loading: false });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.detail || 'Failed to load plans' });
    }
  },

  fetchSubscription: async () => {
    set({ loading: true, error: null });
    try {
      const subscription = await apiService.getSubscription();
      set({ subscription, loading: false });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.detail || 'Failed to load subscription' });
    }
  },

  createCheckout: async (plan: string) => {
    try {
      const result = await apiService.createCheckout(plan);
      return (result.payment_link as string) ?? null;
    } catch (error: any) {
      throw error;
    }
  },

  cancelSubscription: async () => {
    await apiService.cancelSubscription();
    set((state) => ({
      subscription: state.subscription ? { ...state.subscription, subscription: undefined } : null,
    }));
  },
}));
