import { create } from 'zustand';
import { User, AuthState } from '../types';
import apiService from '../services/api';
import { logger } from '../utils/logger';

interface AuthStore extends AuthState {
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (tenantName: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  loadStoredAuth: () => Promise<void>;
  updateUser: (user: User) => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiService.login({ email, password });
      set({
        user: response.user,
        token: response.access_token,
        isAuthenticated: true,
        isLoading: false,
      });
      logger.info('Auth state updated after login', { userId: response.user.id });
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'Login failed';
      set({ isLoading: false, error: errorMessage });
      logger.error('Auth store login failed', { email, errorMessage }, error);
      throw error;
    }
  },

  register: async (tenantName: string, email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await apiService.register({ tenant_name: tenantName, email, password });
      set({
        user: response.user,
        token: response.access_token,
        isAuthenticated: true,
        isLoading: false,
      });
      logger.info('Auth state updated after registration', { userId: response.user.id });
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'Registration failed';
      set({ isLoading: false, error: errorMessage });
      logger.error('Auth store registration failed', { email, errorMessage }, error);
      throw error;
    }
  },

  logout: async () => {
    try {
      await apiService.logout();
      logger.info('Auth state cleared after logout');
    } catch (error) {
      logger.error('Error during logout', {}, error as Error);
    } finally {
      set({
        user: null,
        token: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },

  loadStoredAuth: async () => {
    set({ isLoading: true, error: null });
    try {
      const token = await apiService.getStoredAccessToken();
      const cachedUser = await apiService.getStoredUser();

      if (!token) {
        set({ isLoading: false, isAuthenticated: false, user: null, token: null });
        logger.info('No stored token found, user not authenticated');
        return;
      }

      if (cachedUser) {
        set({ user: cachedUser, token, isAuthenticated: true, isLoading: false });
        logger.info('Loaded cached user from storage', { userId: cachedUser.id });
      }

      const user = await apiService.getCurrentUser();
      set({
        user,
        token,
        isAuthenticated: true,
        isLoading: false,
      });
      logger.info('Auth state loaded from backend', { userId: user.id });
    } catch (error) {
      logger.error('Error loading stored auth', {}, error as Error);
      await apiService.logout();
      set({
        user: null,
        token: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },

  updateUser: (user: User) => {
    set({ user });
  },
}));
