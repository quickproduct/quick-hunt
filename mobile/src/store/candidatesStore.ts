import { create } from 'zustand';
import { Candidate, CandidatesState } from '../types';
import apiService from '../services/api';
import { logger } from '../utils/logger';

interface CandidatesStore extends CandidatesState {
  error: string | null;
  fetchCandidates: () => Promise<void>;
  setActiveCandidate: (candidateId: string) => void;
  createCandidate: (candidate: Partial<Candidate>) => Promise<void>;
  updateCandidate: (candidateId: string, updates: Partial<Candidate>) => Promise<void>;
}

export const useCandidatesStore = create<CandidatesStore>((set, get) => ({
  candidates: [],
  activeCandidateId: '',
  loading: false,
  error: null,

  fetchCandidates: async () => {
    set({ loading: true, error: null });
    try {
      logger.info('Fetching candidates');
      const candidates = await apiService.getCandidates();
      set((state) => ({
        candidates,
        activeCandidateId:
          state.activeCandidateId && candidates.some((candidate) => candidate.id === state.activeCandidateId)
            ? state.activeCandidateId
            : candidates[0]?.id ?? '',
        loading: false,
      }));
      logger.info('Candidates fetched successfully', { count: candidates.length });
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'Failed to load candidates';
      logger.error('Error fetching candidates', { errorMessage }, error);
      set({ candidates: [], loading: false, error: errorMessage });
    }
  },

  setActiveCandidate: (candidateId: string) => {
    logger.info('Active candidate changed', { candidateId });
    set({ activeCandidateId: candidateId });
  },

  createCandidate: async (candidate: Partial<Candidate>) => {
    try {
      logger.info('Creating candidate', { name: candidate.name });
      const newCandidate = await apiService.createCandidate(candidate);
      set(state => ({
        candidates: [...state.candidates, newCandidate],
      }));
      logger.info('Candidate created successfully', { candidateId: newCandidate.id });
    } catch (error) {
      logger.error('Error creating candidate', { name: candidate.name }, error as Error);
      throw error;
    }
  },

  updateCandidate: async (candidateId: string, updates: Partial<Candidate>) => {
    try {
      logger.info('Updating candidate', { candidateId, updates });
      const updatedCandidate = await apiService.updateCandidate(candidateId, updates);
      set(state => ({
        candidates: state.candidates.map(c => 
          c.id === candidateId ? updatedCandidate : c
        ),
      }));
      logger.info('Candidate updated successfully', { candidateId });
    } catch (error) {
      logger.error('Error updating candidate', { candidateId }, error as Error);
      throw error;
    }
  },
}));
