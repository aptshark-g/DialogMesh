/** RightDock — 三屏结构右栏内容坞（youmind 式）。
 *
 * auto 模式: 按当前路由联动默认内容（对话→画像/上下文、图谱→图例…）。
 * fixed 模式: 用户手动固定某内容。
 * 头部 tab 切换内容; 侧边拖拽调整宽度（SidePanel 提供）。
 */
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Settings2, ChevronRight } from 'lucide-react';
import {
  useUIStore,
  useDockContent,
  useSidePanelMode,
  DOCK_TITLES,
} from '@/stores/uiStore';
import type { DockContentKey } from '@/stores/uiStore';
import { cn } from '@/lib/utils';
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

/** 路由 → 默认内容（auto 模式联动映射） */
const ROUTE_DOCK_MAP: { prefix: string; content: DockContentKey }[] = [
  { prefix: '/graph', content: 'legend' },
  { prefix: '/task-planning', content: 'tasks' },
  { prefix: '/engineering', content: 'engineering' },
  { prefix: '/pipeline', content: 'context' },
  { prefix: '/chat', content: 'profile' },
];

function routeDefaultContent(pathname: string): DockContentKey {
  for (const r of ROUTE_DOCK_MAP) {
    if (pathname.startsWith(r.prefix)) return r.content;
  }
  return 'profile';
}

export function RightDock() {
  const location = useLocation();
  const dockContent = useDockContent();
  const mode = useSidePanelMode();
  const setDockContent = useUIStore((s) => s.setDockContent);
  const setSidePanelMode = useUIStore((s) => s.setSidePanelMode);
  const setSidePanelTitle = useUIStore((s) => s.setSidePanelTitle);
  const closeSidePanel = useUIStore((s) => s.closeSidePanel);
  const isOpen = useUIStore((s) => s.sidePanel.isOpen);

  // auto 模式: 路由变化 → 联动默认内容
  useEffect(() => {
    if (mode !== 'auto') return;
    setDockContent(routeDefaultContent(location.pathname));
  }, [location.pathname, mode, setDockContent]);

  // 标题跟随内容
  useEffect(() => {
    setSidePanelTitle(DOCK_TITLES[dockContent]);
  }, [dockContent, setSidePanelTitle]);

  if (!isOpen) return null;

  return (
    <div className="w-full h-full flex flex-col">
      {/* Slim header — 内容选择移入侧栏 DockPicker（B5） */}
      <div className="flex items-center gap-1.5 px-3 py-2 border-b border-subtle shrink-0">
        <h2 className="text-sm font-semibold text-text-primary flex-1 truncate">
          {DOCK_TITLES[dockContent]}
        </h2>
        {/* Mode toggle */}
        <button
          type="button"
          onClick={() => setSidePanelMode(mode === 'auto' ? 'fixed' : 'auto')}
          title={mode === 'auto' ? '联动模式: 随页面切换（点击固定）' : '固定模式: 手动选择（点击恢复联动）'}
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

      {/* Content */}
      <div className="flex-1 overflow-hidden min-h-0">
        {dockContent === 'profile' && <ProfileDockContent />}
        {dockContent === 'context' && <ContextDockContent />}
        {dockContent === 'engineering' && <EngineeringDockContent />}
        {dockContent === 'tasks' && <TasksDockContent />}
        {dockContent === 'legend' && <LegendDockContent />}
        {dockContent === 'thinking' && <ThinkingDockContent />}
        {dockContent === 'heuristics' && <HeuristicsDockContent />}
        {dockContent === 'changelog' && <ChangelogDockContent />}
        {dockContent === 'node_detail' && <NodeDetailDockContent />}
      </div>
    </div>
  );
}
