// FILE: src/components/ui/AboutPopover.tsx
// 「关于」悬浮说明 — 小按钮, 悬停弹出页面用途介绍（不占页面固定空间）

import { useState, useRef } from 'react';
import type { ReactNode } from 'react';
import { Info } from 'lucide-react';
import { cn } from '@/lib/utils';

interface AboutPopoverProps {
  title?: string;
  children: ReactNode;
  align?: 'left' | 'right';
}

export function AboutPopover({ title = '关于', children, align = 'right' }: AboutPopoverProps) {
  const [open, setOpen] = useState(false);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const openPop = () => {
    if (leaveTimer.current) clearTimeout(leaveTimer.current);
    setOpen(true);
  };
  const closePop = () => {
    leaveTimer.current = setTimeout(() => setOpen(false), 120);
  };

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={openPop}
      onMouseLeave={closePop}
      onFocus={openPop}
      onBlur={closePop}
    >
      <button
        type="button"
        aria-label={title}
        title={title}
        className={cn(
          'flex items-center gap-1 rounded-full border border-subtle px-2 py-1 text-[11px]',
          'text-text-muted hover:text-primary hover:border-primary/30 transition-colors'
        )}
      >
        <Info className="w-3 h-3" />
        关于
      </button>
      {open && (
        <div
          className={cn(
            'absolute top-full mt-1.5 w-80 max-w-[80vw] z-dropdown glass-panel rounded-xl p-3 text-xs',
            'text-text-secondary leading-relaxed shadow-card',
            align === 'right' ? 'right-0' : 'left-0'
          )}
          onMouseEnter={openPop}
          onMouseLeave={closePop}
        >
          {children}
        </div>
      )}
    </span>
  );
}
