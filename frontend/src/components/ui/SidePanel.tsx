import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { cn } from '@/lib/utils';

interface SidePanelProps {
  children: ReactNode;
  className?: string;
}

export function SidePanel({ children, className }: SidePanelProps) {
  const isOpen = useUIStore((s) => s.sidePanel.isOpen);
  const width = useUIStore((s) => s.sidePanel.width);
  const closeSidePanel = useUIStore((s) => s.closeSidePanel);
  const toggleSidePanel = useUIStore((s) => s.toggleSidePanel);
  const setSidePanelWidth = useUIStore((s) => s.setSidePanelWidth);
  const resizingRef = useRef(false);

  const onResizeStart = (e: React.PointerEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    const startX = e.clientX;
    const startWidth = useUIStore.getState().sidePanel.width;
    const onMove = (ev: PointerEvent) => {
      if (!resizingRef.current) return;
      setSidePanelWidth(startWidth + (startX - ev.clientX));
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
      if (e.key === 'Escape' && isOpen) {
        closeSidePanel();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isOpen, closeSidePanel]);

  return (
    <>
      {/* Mobile Overlay */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-black/40 z-drawer lg:hidden"
            onClick={closeSidePanel}
            role="presentation"
          />
        )}
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.aside
            initial={false}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className={cn(
              'flex flex-col shrink-0 relative',
              'fixed inset-y-0 right-0 z-drawer lg:static lg:z-auto',
              'lg:mt-2 lg:mb-3 lg:mr-3 lg:ml-1.5',
              className
            )}
            style={{ width }}
          >
            {/* Resize handle — 横跨卡片左缘与栏间缝隙（desktop） */}
            <div
              onPointerDown={onResizeStart}
              className="group absolute -left-1.5 top-0 bottom-0 w-3 py-2 cursor-col-resize hidden lg:block z-10"
              aria-label="调整右栏宽度"
            >
              <div className="ml-auto h-full w-1 rounded-full group-hover:bg-primary/30 group-active:bg-primary/40 transition-colors" />
            </div>
            {/* P0-C: 浮动卡片外壳 — 发色/圆角/裁剪在内层, aside 仅作定位壳（移动端仍为全尺寸抽屉） */}
            <div className="h-full flex flex-col bg-surface-dock lg:rounded-dock overflow-hidden" style={{ width }}>
              {children}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {!isOpen && (
          <motion.button
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 10 }}
            transition={{ duration: 0.2 }}
            type="button"
            onClick={toggleSidePanel}
            className="fixed lg:absolute right-0 top-1/2 -translate-y-1/2 z-30 p-1.5 bg-surface-card border border-subtle border-r-0 rounded-l-md shadow-card hover:bg-surface-card-hover text-text-secondary transition-colors"
            aria-label="展开右侧面板"
          >
            <ChevronRight className="w-4 h-4" />
          </motion.button>
        )}
      </AnimatePresence>
    </>
  );
}
