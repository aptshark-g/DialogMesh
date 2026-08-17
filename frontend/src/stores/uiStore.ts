// FILE: src/stores/uiStore.ts

import { create } from 'zustand';
import type { ReactNode } from 'react';

export type DockContentKey = 'profile' | 'chat' | 'context' | 'engineering' | 'tasks' | 'legend' | 'thinking' | 'heuristics' | 'changelog' | 'node_detail';

export const DOCK_TITLES: Record<DockContentKey, string> = {
  profile: '认知画像',
  chat: '对话',
  context: '上下文',
  engineering: '工程链',
  tasks: '任务',
  legend: '图例',
  thinking: '思考流',
  heuristics: '启发',
  changelog: '变更日志',
  node_detail: '节点详情',
};

/** 右键"在右侧显示详情"的节点数据（B5） */
export interface InspectNodeData {
  id: string;
  label?: string;
  type?: string;
  intent?: string;
  depth?: number;
  temperature?: string;
  size?: number;
  entities?: string[];
  raw_text?: string;
  summary?: string;
  state?: Record<string, unknown>;
  edges?: { source: string; target: string; type?: string }[];
}

const SIDEPANEL_WIDTH_KEY = 'dm_sidepanel_width';
const CENTERPANEL_WIDTH_KEY = 'dm_centerpanel_width';
const SIDEPANEL_MIN = 280;
const SIDEPANEL_MAX = 560;
const CENTERPANEL_MIN = 360;
const CENTERPANEL_MAX = 720;
const SIDEBAR_WIDTH_KEY = 'dm_sidebar_width';
const SIDEBAR_MIN = 180;
const SIDEBAR_MAX = 320;

function loadInitialWidth(): number {
  try {
    const v = parseInt(localStorage.getItem(SIDEPANEL_WIDTH_KEY) || '', 10);
    if (v >= SIDEPANEL_MIN && v <= SIDEPANEL_MAX) return v;
  } catch {}
  // P0-D 比例: 默认 340→320, 贴近 mockup v2 dock(316px)
  return 320;
}

function loadInitialCenterWidth(): number {
  try {
    const v = parseInt(localStorage.getItem(CENTERPANEL_WIDTH_KEY) || '', 10);
    if (v >= CENTERPANEL_MIN && v <= CENTERPANEL_MAX) return v;
  } catch {}
  return 480;
}

function loadInitialSidebarWidth(): number {
  try {
    const v = parseInt(localStorage.getItem(SIDEBAR_WIDTH_KEY) || '', 10);
    if (v >= SIDEBAR_MIN && v <= SIDEBAR_MAX) return v;
  } catch {}
  return 228;
}

interface SidePanelState {
  isOpen: boolean;
  title: string;
  width: number;
  mode: 'auto' | 'fixed';
  dockContent: DockContentKey;
}

interface CenterPanelState {
  isOpen: boolean;
  width: number;
}

interface ModalState {
  isOpen: boolean;
  title: string;
  content: ReactNode | null;
  confirmText: string;
  cancelText: string;
  onConfirm: (() => void) | null;
  onCancel: (() => void) | null;
  closeOnOverlay: boolean;
}

export interface UIStore {
  sidePanel: SidePanelState;
  /** B5（2026-08-07）: 内容坞显示位置 — 右侧 Dock 或 中间浮层 */
  dockPlacement: 'right' | 'center';
  centerPanel: CenterPanelState;
  inspectNode: InspectNodeData | null;
  modal: ModalState;

  openSidePanel: (opts?: Partial<Omit<SidePanelState, 'isOpen'>>) => void;
  closeSidePanel: () => void;
  toggleSidePanel: () => void;
  setSidePanelTitle: (title: string) => void;
  setSidePanelMode: (mode: 'auto' | 'fixed') => void;
  setDockContent: (dockContent: DockContentKey) => void;
  setSidePanelWidth: (width: number) => void;
  setDockPlacement: (placement: 'right' | 'center') => void;
  openCenterPanel: () => void;
  closeCenterPanel: () => void;
  setCenterPanelWidth: (width: number) => void;
  /** P1-H: 左侧栏可拖拽宽度 */
  sidebarWidth: number;
  setSidebarWidth: (width: number) => void;
  setInspectNode: (node: InspectNodeData | null) => void;

  openModal: (opts: Partial<Omit<ModalState, 'isOpen'>>) => void;
  closeModal: () => void;
  confirm: (opts: {
    title: string;
    message: ReactNode;
    onConfirm?: () => void;
    onCancel?: () => void;
    confirmText?: string;
    cancelText?: string;
  }) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  sidePanel: {
    isOpen: true,
    title: '认知画像',
    width: loadInitialWidth(),
    mode: 'auto',
    dockContent: 'profile',
  },
  dockPlacement: 'right',
  centerPanel: {
    isOpen: false,
    width: loadInitialCenterWidth(),
  },
  sidebarWidth: loadInitialSidebarWidth(),
  inspectNode: null,
  modal: {
    isOpen: false,
    title: '',
    content: null,
    confirmText: '确认',
    cancelText: '取消',
    onConfirm: null,
    onCancel: null,
    closeOnOverlay: true,
  },

  openSidePanel: (opts) =>
    set((s) => ({
      sidePanel: { ...s.sidePanel, isOpen: true, ...opts },
    })),
  closeSidePanel: () =>
    set((s) => ({
      sidePanel: { ...s.sidePanel, isOpen: false },
    })),
  toggleSidePanel: () =>
    set((s) => ({
      sidePanel: { ...s.sidePanel, isOpen: !s.sidePanel.isOpen },
    })),
  setSidePanelTitle: (title) =>
    set((s) => ({
      sidePanel: { ...s.sidePanel, title },
    })),
  setSidePanelMode: (mode) =>
    set((s) => ({
      sidePanel: { ...s.sidePanel, mode },
    })),
  setDockContent: (dockContent) =>
    set((s) => ({
      sidePanel: { ...s.sidePanel, dockContent },
    })),
  setSidePanelWidth: (width) => {
    const w = Math.min(SIDEPANEL_MAX, Math.max(SIDEPANEL_MIN, Math.round(width)));
    try {
      localStorage.setItem(SIDEPANEL_WIDTH_KEY, String(w));
    } catch {}
    set((s) => ({
      sidePanel: { ...s.sidePanel, width: w },
    }));
  },
  setDockPlacement: (placement) =>
    set((s) => ({
      dockPlacement: placement,
      // 切换位置时只保留目标位置的容器；源容器关闭避免同内容双开
      sidePanel: { ...s.sidePanel, isOpen: placement === 'right' ? s.sidePanel.isOpen : false },
      centerPanel: { ...s.centerPanel, isOpen: placement === 'center' ? s.centerPanel.isOpen : false },
    })),
  openCenterPanel: () =>
    set((s) => ({
      centerPanel: { ...s.centerPanel, isOpen: true },
      sidePanel: { ...s.sidePanel, isOpen: false },
    })),
  closeCenterPanel: () =>
    set((s) => ({
      centerPanel: { ...s.centerPanel, isOpen: false },
    })),
  setCenterPanelWidth: (width) => {
    const w = Math.min(CENTERPANEL_MAX, Math.max(CENTERPANEL_MIN, Math.round(width)));
    try {
      localStorage.setItem(CENTERPANEL_WIDTH_KEY, String(w));
    } catch {}
    set((s) => ({
      centerPanel: { ...s.centerPanel, width: w },
    }));
  },
  setSidebarWidth: (width) => {
    const w = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, Math.round(width)));
    try { localStorage.setItem(SIDEBAR_WIDTH_KEY, String(w)); } catch {}
    set({ sidebarWidth: w });
  },
  setInspectNode: (node) =>
    set({ inspectNode: node }),

  openModal: (opts) =>
    set((s) => ({
      modal: { ...s.modal, isOpen: true, ...opts },
    })),
  closeModal: () =>
    set((s) => ({
      modal: {
        ...s.modal,
        isOpen: false,
        content: null,
        onConfirm: null,
        onCancel: null,
      },
    })),
  confirm: (opts) =>
    set((s) => ({
      modal: {
        ...s.modal,
        isOpen: true,
        title: opts.title,
        content: opts.message,
        confirmText: opts.confirmText ?? '确认',
        cancelText: opts.cancelText ?? '取消',
        onConfirm: opts.onConfirm ?? null,
        onCancel: opts.onCancel ?? null,
        closeOnOverlay: true,
      },
    })),
}));

export function useSidePanelOpen(): boolean {
  return useUIStore((s) => s.sidePanel.isOpen);
}

export function useSidePanelTitle(): string {
  return useUIStore((s) => s.sidePanel.title);
}

export function useSidePanelWidth(): number {
  return useUIStore((s) => s.sidePanel.width);
}

export function useSidePanelMode(): 'auto' | 'fixed' {
  return useUIStore((s) => s.sidePanel.mode);
}

export function useDockContent(): DockContentKey {
  return useUIStore((s) => s.sidePanel.dockContent);
}
