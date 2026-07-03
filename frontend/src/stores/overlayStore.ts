import { create } from 'zustand';

export interface OverlayState {
  isOpen: boolean;
  isMinimized: boolean;
  position: 'bottom-right' | 'bottom-left' | 'bottom-center';
  unreadCount: number;
  badgeVisible: boolean;
}

export interface OverlayActions {
  open: () => void;
  close: () => void;
  toggle: () => void;
  minimize: () => void;
  maximize: () => void;
  setPosition: (position: OverlayState['position']) => void;
  incrementUnread: () => void;
  clearUnread: () => void;
  setBadgeVisible: (visible: boolean) => void;
}

export const useOverlayStore = create<OverlayState & OverlayActions>((set) => ({
  isOpen: false,
  isMinimized: false,
  position: 'bottom-right',
  unreadCount: 0,
  badgeVisible: false,

  open: () => set({ isOpen: true, isMinimized: false, badgeVisible: false }),
  close: () => set({ isOpen: false, isMinimized: false }),
  toggle: () => set((state) => ({ isOpen: !state.isOpen, isMinimized: false, badgeVisible: false })),
  minimize: () => set({ isMinimized: true }),
  maximize: () => set({ isMinimized: false }),
  setPosition: (position) => set({ position }),
  incrementUnread: () => set((state) => ({ unreadCount: state.unreadCount + 1, badgeVisible: true })),
  clearUnread: () => set({ unreadCount: 0, badgeVisible: false }),
  setBadgeVisible: (visible) => set({ badgeVisible: visible }),
}));

export function useOverlayOpen(): boolean {
  return useOverlayStore((s) => s.isOpen);
}

export function useOverlayMinimized(): boolean {
  return useOverlayStore((s) => s.isMinimized);
}

export function useOverlayPosition(): OverlayState['position'] {
  return useOverlayStore((s) => s.position);
}

export function useOverlayUnreadCount(): number {
  return useOverlayStore((s) => s.unreadCount);
}

export function useOverlayBadgeVisible(): boolean {
  return useOverlayStore((s) => s.badgeVisible);
}
