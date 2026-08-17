/** RightDock — 副槽容器(P1-A 双槽位)。
 *
 *  头部三件套:
 *   - 表面切换器: 标题即按钮, 下拉列出注册表全部表面; 手动选择 → fixed + 记忆配对;
 *   - 交换⇄: 副槽表面与当前主槽页面互换(双方互有形态时可用, 见 surfaceRegistry.getSwapTarget);
 *   - 联动/固定: auto 随路由配对(用户记忆优先), fixed 保持手动选择。
 */
import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Settings2, ChevronRight, ChevronDown, ArrowLeftRight, Check, Maximize2 } from 'lucide-react';
import { useUIStore, useDockContent, useSidePanelMode } from '@/stores/uiStore';
import { specMove } from '@/lib/spec';
import { useLayoutStore } from '@/lib/layoutStore';
import {
  SURFACES,
  SURFACE_MAP,
  routePrefix,
  defaultSurfaceFor,
  getSwapTarget,
} from '@/lib/surfaceRegistry';
import type { SurfaceKey } from '@/lib/surfaceRegistry';
import { cn } from '@/lib/utils';

export function RightDock() {
  const location = useLocation();
  const navigate = useNavigate();
  const dockContent = useDockContent();
  const mode = useSidePanelMode();
  const setDockContent = useUIStore((s) => s.setDockContent);
  const setSidePanelMode = useUIStore((s) => s.setSidePanelMode);
  const setSidePanelTitle = useUIStore((s) => s.setSidePanelTitle);
  const closeSidePanel = useUIStore((s) => s.closeSidePanel);
  const openCenterPanel = useUIStore((s) => s.openCenterPanel);
  const isOpen = useUIStore((s) => s.sidePanel.isOpen);
  const pairing = useLayoutStore((s) => s.pairing);
  const rememberPairing = useLayoutStore((s) => s.rememberPairing);
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [switcherHover, setSwitcherHover] = useState<string | null>(null);

  // auto(联动): 路由变化 → 用户记忆优先, 其次注册表默认配对
  useEffect(() => {
    if (mode !== 'auto') return;
    const p = routePrefix(location.pathname);
    setDockContent(pairing[p] ?? defaultSurfaceFor(location.pathname));
  }, [location.pathname, mode, pairing, setDockContent]);

  // 标题跟随内容(供移动端/其他壳读取)
  useEffect(() => {
    setSidePanelTitle(SURFACE_MAP[dockContent].title);
  }, [dockContent, setSidePanelTitle]);

  if (!isOpen) return null;

  const active = SURFACE_MAP[dockContent];
  const ActiveIcon = active.icon;
  const ActiveSurface = active.component;
  const swap = getSwapTarget(location.pathname, dockContent);

  const chooseSurface = (key: SurfaceKey) => {
    setDockContent(key);
    setSidePanelMode('fixed');
    rememberPairing(routePrefix(location.pathname), key);
    setSwitcherOpen(false);
  };

  const doSwap = () => {
    if (!swap) return;
    setSidePanelMode('fixed');
    setDockContent(swap.newSide);
    rememberPairing(routePrefix(swap.navigateTo), swap.newSide);
    navigate(swap.navigateTo);
  };

  return (
    <div className="w-full h-full flex flex-col min-h-0">
      {/* 头部: 切换器 + 交换 + 联动/固定 + 转悬浮 + 收起 */}
      <div className="flex items-center gap-1 px-3 pt-3.5 pb-2 shrink-0">
        {/* 表面切换器 */}
        <div className="relative flex-1 min-w-0">
          <button
            type="button"
            onClick={() => setSwitcherOpen((v) => !v)}
            aria-label="切换副槽内容"
            className="flex items-center gap-1.5 max-w-full px-2.5 py-[5px] rounded-full bg-wash hover:bg-wash-strong transition-colors"
          >
            <ActiveIcon className="w-3.5 h-3.5 text-text-muted shrink-0" />
            <span className="text-xs font-medium text-text-primary truncate">
              {active.title}
            </span>
            <ChevronDown className="w-3 h-3 text-text-muted shrink-0" />
          </button>
          {switcherOpen && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setSwitcherOpen(false)}
                role="presentation"
              />
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.12 }}
                onPointerMove={specMove}
                className="spec-panel absolute left-0 top-full mt-1 z-50 w-44 rounded-xl glass-panel overflow-hidden"
              >
                <div className="py-1" onMouseLeave={() => setSwitcherHover(null)}>
                  {SURFACES.map((s) => {
                    const Icon = s.icon;
                    const isActive = s.key === dockContent;
                    return (
                      <button
                        key={s.key}
                        type="button"
                        onClick={() => chooseSurface(s.key)}
                        onMouseEnter={() => setSwitcherHover(s.key)}
                        className={cn(
                          'relative w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs transition-colors',
                          isActive
                            ? 'text-primary font-medium'
                            : 'text-text-secondary hover:text-text-primary'
                        )}
                      >
                        {!isActive && switcherHover === s.key && (
                          <motion.span
                            layoutId="dock-switcher-pill"
                            className="absolute inset-0 rounded-md bg-wash pointer-events-none"
                            transition={{ type: 'spring', stiffness: 700, damping: 45 }}
                          />
                        )}
                        <Icon className="w-3.5 h-3.5 shrink-0" />
                        <span className="flex-1 truncate">{s.label}</span>
                        {isActive && <Check className="w-3 h-3 shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              </motion.div>
            </>
          )}
        </div>

        {/* 交换⇄ */}
        <button
          type="button"
          onClick={doSwap}
          disabled={!swap}
          title={
            swap
              ? `与主区交换 ⇄(主区打开「${active.label}」,副槽变为「${SURFACE_MAP[swap.newSide].label}」)`
              : '当前组合不可交换'
          }
          aria-label="与主区交换"
          className="p-1.5 rounded-md text-text-muted hover:text-text-secondary hover:bg-surface-card-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ArrowLeftRight className="w-3.5 h-3.5" />
        </button>

        {/* 联动/固定 */}
        <button
          type="button"
          onClick={() => setSidePanelMode(mode === 'auto' ? 'fixed' : 'auto')}
          title={mode === 'auto' ? '联动模式: 随页面切换(点击固定)' : '固定模式: 手动选择(点击恢复联动)'}
          className={cn(
            'flex items-center gap-1 px-1.5 py-1 rounded text-[10px] transition-colors',
            mode === 'auto'
              ? 'text-primary bg-primary/5 hover:bg-primary/10'
              : 'text-text-muted hover:text-text-secondary hover:bg-surface-card-hover'
          )}
        >
          <Settings2 className="w-3 h-3" />
          <span className="hidden lg:inline">{mode === 'auto' ? '联动' : '固定'}</span>
        </button>

        {/* 转悬浮: 副槽 → 中间浮层(P1-C placement 归坞头, DockPicker 退出侧栏) */}
        <button
          type="button"
          onClick={() => { openCenterPanel(); closeSidePanel(); }}
          title="转为悬浮显示(中间浮层)"
          aria-label="转为悬浮显示"
          className="p-1 rounded text-text-muted hover:text-text-secondary hover:bg-surface-card-hover transition-colors"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>

        {/* 收起 */}
        <button
          type="button"
          onClick={closeSidePanel}
          title="收起右栏"
          className="p-1 rounded text-text-muted hover:text-text-secondary hover:bg-surface-card-hover transition-colors"
          aria-label="收起右栏"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 内容 — 注册表驱动 */}
      <div className="flex-1 overflow-hidden min-h-0">
        <ActiveSurface />
      </div>
    </div>
  );
}
