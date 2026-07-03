// FILE: src/stores/uiStore.ts

import { create } from 'zustand';
import type { ReactNode } from 'react';

interface SidePanelState {
  isOpen: boolean;
  title: string;
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
  modal: ModalState;

  openSidePanel: (opts?: Partial<Omit<SidePanelState, 'isOpen'>>) => void;
  closeSidePanel: () => void;
  toggleSidePanel: () => void;
  setSidePanelTitle: (title: string) => void;

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
    width: 340,
  },
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
