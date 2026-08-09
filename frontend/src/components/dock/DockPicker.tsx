/**
 * DockPicker — 侧栏内容坞选择器（B5, 2026-08-07）。
 *
 * 用户交互（三屏结构 + 联动选择）:
 *   - 左侧两个按钮:「悬浮」「嵌入」, 鼠标放上去即打开该位置的内容坞
 *     （live preview）; 点击固定/取消固定。
 *   - hover 弹出的内容列表可切换具体内容（画像/上下文/工程链/任务/图例/
 *     思考流/启发/变更日志）; hover 列表项实时切换, 点击固定。
 */
import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Maximize2, PanelRight, ChevronRight } from 'lucide-react';
import {
  useUIStore,
  useDockContent,
  DOCK_TITLES,
} from '@/stores/uiStore';
import { DOCK_TABS } from './dockTabs';
import { cn } from '@/lib/utils';

type Placement = 'right' | 'center';

export function DockPicker() {
  const dockContent = useDockContent();
  const setDockContent = useUIStore((s) => s.setDockContent);
  const setSidePanelMode = useUIStore((s) => s.setSidePanelMode);
  const openSidePanel = useUIStore((s) => s.openSidePanel);
  const closeSidePanel = useUIStore((s) => s.closeSidePanel);
  const openCenterPanel = useUIStore((s) => s.openCenterPanel);
  const closeCenterPanel = useUIStore((s) => s.closeCenterPanel);
  const setDockPlacement = useUIStore((s) => s.setDockPlacement);
  const sideOpen = useUIStore((s) => s.sidePanel.isOpen);
  const centerOpen = useUIStore((s) => s.centerPanel.isOpen);

  const [hoverPlacement, setHoverPlacement] = useState<Placement | null>(null);
  const [pinned, setPinned] = useState<Placement | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showIn = (placement: Placement, open: boolean) => {
    setDockPlacement(placement);
    if (open) {
      if (placement === 'right') openSidePanel();
      else openCenterPanel();
    } else {
      if (placement === 'right') closeSidePanel();
      else closeCenterPanel();
    }
  };

  const handleButtonEnter = (placement: Placement) => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setHoverPlacement(placement);
    setPickerOpen(true);
    if (!pinned) showIn(placement, true);
  };

  const handleGroupLeave = () => {
    closeTimer.current = setTimeout(() => {
      setHoverPlacement(null);
      setPickerOpen(false);
      if (!pinned) {
        closeSidePanel();
        closeCenterPanel();
      }
    }, 180);
  };

  const handleButtonClick = (placement: Placement) => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    const next = pinned === placement ? null : placement;
    setPinned(next);
    showIn(placement, next !== null);
    setHoverPlacement(placement);
    setPickerOpen(true);
  };

  const applyContent = (key: (typeof DOCK_TABS)[number]['key']) => {
    setDockContent(key);
    setSidePanelMode('fixed'); // 手动选择内容 = 固定模式
  };

  const placementLabel =
    hoverPlacement === 'center' ? '悬浮显示' :
    hoverPlacement === 'right' ? '嵌入显示' : '选择显示位置';

  return (
    <div
      className="relative shrink-0"
      onMouseLeave={handleGroupLeave}
    >
      <div className="px-3 pt-1 pb-0.5">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onMouseEnter={() => handleButtonEnter('center')}
            onClick={() => handleButtonClick('center')}
            title="内容坞悬浮显示（hover 预览, 点击固定）"
            className={cn(
              'flex flex-1 items-center justify-center gap-1.5 px-2 py-2 rounded-lg border transition-colors text-[11px] font-medium',
              centerOpen
                ? 'border-primary/40 bg-primary/10 text-primary'
                : 'border-subtle bg-surface-card text-text-secondary hover:bg-surface-card-hover hover:text-primary'
            )}
          >
            <Maximize2 className="w-3.5 h-3.5 shrink-0" />
            悬浮
          </button>
          <button
            type="button"
            onMouseEnter={() => handleButtonEnter('right')}
            onClick={() => handleButtonClick('right')}
            title="内容坞嵌入显示（hover 预览, 点击固定）"
            className={cn(
              'flex flex-1 items-center justify-center gap-1.5 px-2 py-2 rounded-lg border transition-colors text-[11px] font-medium',
              sideOpen
                ? 'border-primary/40 bg-primary/10 text-primary'
                : 'border-subtle bg-surface-card text-text-secondary hover:bg-surface-card-hover hover:text-primary'
            )}
          >
            <PanelRight className="w-3.5 h-3.5 shrink-0" />
            嵌入
          </button>
        </div>
      </div>

      {/* Hover popover — 内容列表 */}
      <AnimatePresence>
        {pickerOpen && (
          <motion.div
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -6 }}
            transition={{ duration: 0.15 }}
            className="absolute left-full top-0 ml-1.5 z-50 w-56 rounded-xl border border-subtle bg-surface-card shadow-2xl overflow-hidden"
            onMouseEnter={() => {
              if (closeTimer.current) clearTimeout(closeTimer.current);
              setPickerOpen(true);
            }}
          >
            <div className="px-3 py-2 border-b border-subtle flex items-center justify-between">
              <span className="text-xs font-semibold text-text-primary">内容坞</span>
              <span className="text-[10px] text-primary">{placementLabel}</span>
            </div>
            <div className="py-1.5">
              {DOCK_TABS.map((tab) => {
                const Icon = tab.icon;
                const active = dockContent === tab.key;
                return (
                  <button
                    key={tab.key}
                    type="button"
                    onMouseEnter={() => applyContent(tab.key)}
                    onClick={() => {
                      applyContent(tab.key);
                      // 点击 = 固定当前 hover 位置
                      const placement = hoverPlacement || 'right';
                      setPinned(placement);
                      showIn(placement, true);
                    }}
                    className={cn(
                      'w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors',
                      active
                        ? 'bg-primary/10 text-primary font-medium'
                        : 'text-text-secondary hover:bg-surface-card-hover hover:text-text-primary'
                    )}
                  >
                    <Icon className="w-3.5 h-3.5 shrink-0" />
                    <span className="flex-1 truncate">{tab.label}</span>
                    <span className="text-[10px] text-text-muted truncate max-w-[90px]">
                      {DOCK_TITLES[tab.key]}
                    </span>
                    {active && <ChevronRight className="w-3 h-3 shrink-0" />}
                  </button>
                );
              })}
            </div>
            <div className="px-3 py-1.5 border-t border-subtle text-[10px] text-text-muted">
              hover 实时切换 · 点击固定位置 · 离开自动收起
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
