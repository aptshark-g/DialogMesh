/** 万能搜索栏(omnibox)开合状态 — 触发器在 Toolbar, 面板挂在 Layout, 全局 ⌘K/Ctrl+K。 */
import { create } from 'zustand';

interface OmniboxState {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
}

export const useOmnibox = create<OmniboxState>((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
  toggle: () => set((s) => ({ open: !s.open })),
}));
