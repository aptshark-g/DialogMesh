// FILE: src/stores/profileStore.ts

import { create } from 'zustand';
import type {
  CognitiveProfile,
  ProfileStats,
  IntentDistribution,
  RadarDataPoint,
} from '../types/profile';

export interface ProfileState {
  profiles: CognitiveProfile[];
  selectedProfileId: string | null;
  isLoading: boolean;
  error: string | null;
  aggregatedStats: ProfileStats | null;
  intentDistribution: IntentDistribution[];
  radarData: RadarDataPoint[];
}

export interface ProfileActions {
  setProfiles: (profiles: CognitiveProfile[]) => void;
  selectProfile: (id: string | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setAggregatedStats: (stats: ProfileStats | null) => void;
  setIntentDistribution: (distribution: IntentDistribution[]) => void;
  setRadarData: (data: RadarDataPoint[]) => void;
  addProfile: (profile: CognitiveProfile) => void;
  clearProfiles: () => void;
}

export type ProfileStore = ProfileState & ProfileActions;

const initialState: ProfileState = {
  profiles: [],
  selectedProfileId: null,
  isLoading: false,
  error: null,
  aggregatedStats: null,
  intentDistribution: [],
  radarData: [],
};

export const useProfileStore = create<ProfileStore>((set) => ({
  ...initialState,

  setProfiles: (profiles) => set({ profiles }),

  selectProfile: (id) => set({ selectedProfileId: id }),

  setLoading: (loading) => set({ isLoading: loading }),

  setError: (error) => set({ error }),

  setAggregatedStats: (stats) => set({ aggregatedStats: stats }),

  setIntentDistribution: (distribution) => set({ intentDistribution: distribution }),

  setRadarData: (data) => set({ radarData: data }),

  addProfile: (profile) =>
    set((state) => ({
      profiles: [profile, ...state.profiles],
    })),

  clearProfiles: () => set({ profiles: [], selectedProfileId: null }),
}));

// ==================== Selector hooks ====================

export function useProfiles(): CognitiveProfile[] {
  return useProfileStore((s) => s.profiles);
}

export function useSelectedProfile(): CognitiveProfile | null {
  return useProfileStore((s) =>
    s.profiles.find((p) => p.id === s.selectedProfileId) ?? null
  );
}

export function useProfileLoading(): boolean {
  return useProfileStore((s) => s.isLoading);
}

export function useProfileError(): string | null {
  return useProfileStore((s) => s.error);
}

export function useAggregatedStats(): ProfileStats | null {
  return useProfileStore((s) => s.aggregatedStats);
}

export function useIntentDistribution(): IntentDistribution[] {
  return useProfileStore((s) => s.intentDistribution);
}

export function useRadarData(): RadarDataPoint[] {
  return useProfileStore((s) => s.radarData);
}
