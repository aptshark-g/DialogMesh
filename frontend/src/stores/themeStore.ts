// FILE: src/stores/themeStore.ts

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Theme = 'dark' | 'light';

interface ThemeState {
  theme: Theme;
}

interface ThemeActions {
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

interface ThemeStore extends ThemeState, ThemeActions {}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set, get) => ({
      theme: 'dark' as Theme,

      toggleTheme: () => {
        const next = get().theme === 'dark' ? 'light' : 'dark';
        set({ theme: next });
        // Sync to HTML class for Tailwind dark mode
        if (next === 'dark') {
          document.documentElement.classList.remove('light');
          document.documentElement.classList.add('dark');
        } else {
          document.documentElement.classList.remove('dark');
          document.documentElement.classList.add('light');
        }
      },

      setTheme: (theme: Theme) => {
        set({ theme });
        if (theme === 'dark') {
          document.documentElement.classList.remove('light');
          document.documentElement.classList.add('dark');
        } else {
          document.documentElement.classList.remove('dark');
          document.documentElement.classList.add('light');
        }
      },
    }),
    {
      name: 'dialogmesh-theme',
      version: 1,
      onRehydrateStorage: () => (state) => {
        if (state) {
          const theme = state.theme;
          if (theme === 'dark') {
            document.documentElement.classList.remove('light');
            document.documentElement.classList.add('dark');
          } else {
            document.documentElement.classList.remove('dark');
            document.documentElement.classList.add('light');
          }
        }
      },
    }
  )
);

// ==================== Selector hook ====================

export function useTheme(): Theme {
  return useThemeStore((s) => s.theme);
}

export function useToggleTheme(): () => void {
  return useThemeStore((s) => s.toggleTheme);
}

export function useSetTheme(): (theme: Theme) => void {
  return useThemeStore((s) => s.setTheme);
}
