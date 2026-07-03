import { useEffect } from 'react';
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
            initial={{ width: 0, opacity: 0 }}
            animate={{ width, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className={cn(
              'bg-surface-sidebar border-l border-subtle flex flex-col shrink-0 overflow-hidden',
              'fixed inset-y-0 right-0 z-drawer lg:static lg:z-auto',
              className
            )}
            style={{ width }}
          >
            <div className="h-full flex flex-col" style={{ width }}>
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
