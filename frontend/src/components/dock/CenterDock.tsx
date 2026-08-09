/**
 * CenterDock — 内容坞"悬浮"浮层（B5, 2026-08-07）。
 * 覆盖在主内容区右侧, 可拖左边缘调宽（360-720, 持久化）, Esc/× 关闭。
 * 内容与右侧 Dock 共享（DockContents[dockContent]）。
 */
import { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { useUIStore, useDockContent, DOCK_TITLES } from '@/stores/uiStore';
import {
  ProfileDockContent,
  ContextDockContent,
  EngineeringDockContent,
  TasksDockContent,
  LegendDockContent,
  ThinkingDockContent,
  HeuristicsDockContent,
  ChangelogDockContent,
  NodeDetailDockContent,
} from './DockContents';

const CENTER_CONTENTS = {
  profile: ProfileDockContent,
  context: ContextDockContent,
  engineering: EngineeringDockContent,
  tasks: TasksDockContent,
  legend: LegendDockContent,
  thinking: ThinkingDockContent,
  heuristics: HeuristicsDockContent,
  changelog: ChangelogDockContent,
  node_detail: NodeDetailDockContent,
} as const;

export function CenterDock() {
  const isOpen = useUIStore((s) => s.centerPanel.isOpen);
  const width = useUIStore((s) => s.centerPanel.width);
  const dockContent = useDockContent();
  const closeCenterPanel = useUIStore((s) => s.closeCenterPanel);
  const setCenterPanelWidth = useUIStore((s) => s.setCenterPanelWidth);
  const resizingRef = useRef(false);

  const onResizeStart = (e: React.PointerEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    const startX = e.clientX;
    const startWidth = useUIStore.getState().centerPanel.width;
    const onMove = (ev: PointerEvent) => {
      if (!resizingRef.current) return;
      // 左边缘拖动: 往左拖变宽
      setCenterPanelWidth(startWidth + (startX - ev.clientX));
    };
    const onUp = () => {
      resizingRef.current = false;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) closeCenterPanel();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isOpen, closeCenterPanel]);

  const Content = CENTER_CONTENTS[dockContent];

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.aside
          initial={{ x: 40, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 40, opacity: 0 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="absolute inset-y-0 right-0 z-30 flex flex-col bg-surface-sidebar border-l border-subtle shadow-2xl overflow-hidden"
          style={{ width }}
          aria-label="悬浮内容坞"
        >
          {/* Resize handle — 拖左边缘调宽 */}
          <div
            onPointerDown={onResizeStart}
            className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/30 active:bg-primary/40 z-10"
            aria-label="调整中间栏宽度"
          />
          <div className="flex items-center gap-2 px-3 py-2 border-b border-subtle shrink-0">
            <h2 className="text-sm font-semibold text-text-primary flex-1 truncate">
              {DOCK_TITLES[dockContent]}
            </h2>
            <span className="text-[10px] text-text-muted">悬浮显示</span>
            <button
              type="button"
              onClick={closeCenterPanel}
              className="p-1.5 rounded-md hover:bg-surface-card-hover text-text-muted hover:text-text-primary transition-colors"
              aria-label="关闭悬浮内容坞"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            <Content />
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
