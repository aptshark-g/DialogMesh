/** 表面注册表(P1-A 双槽位骨架)。
 *
 *  每个"表面"声明: key / 短名 / 标题 / 图标 / 副槽组件形态 / 可选主槽路由形态。
 *  槽位与表面解耦:
 *   - 副槽(dock)可通过头部切换器换成任意表面;
 *   - 主槽是路由页面;
 *   - 交换⇄ 仅在「副槽表面有主槽形态 且 当前主槽页面有副槽形态」时可用,
 *     见 getSwapTarget。例: 主槽 /tasks + 副槽对话 → 交换后 主槽 /chat + 副槽任务。
 */
import type { ComponentType } from 'react';
import {
  User,
  Braces,
  GitBranch,
  ListChecks,
  Palette,
  BrainCircuit,
  Lightbulb,
  History,
  Info,
  MessageSquare,
} from 'lucide-react';
import type { DockContentKey } from '@/stores/uiStore';
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
} from '@/components/dock/DockContents';
import { ChatSideSurface } from '@/components/dock/ChatSideSurface';

/** 'chat' 已并入 uiStore 的 DockContentKey, SurfaceKey 即其别名 */
export type SurfaceKey = DockContentKey;

export interface SurfaceDef {
  key: SurfaceKey;
  /** 短名(切换器列表/DockPicker 用) */
  label: string;
  /** 副槽头部标题 */
  title: string;
  icon: ComponentType<{ className?: string }>;
  /** 副槽形态组件 */
  component: ComponentType;
  /** 主槽形态路由; 无则该表面不可交换到主槽 */
  mainRoute?: string;
}

export const SURFACES: readonly SurfaceDef[] = [
  { key: 'profile', label: '画像', title: '认知画像', icon: User, component: ProfileDockContent, mainRoute: '/profile' },
  { key: 'chat', label: '对话', title: '对话', icon: MessageSquare, component: ChatSideSurface, mainRoute: '/chat' },
  { key: 'context', label: '上下文', title: '上下文', icon: Braces, component: ContextDockContent, mainRoute: '/pipeline' },
  { key: 'engineering', label: '工程链', title: '工程链', icon: GitBranch, component: EngineeringDockContent, mainRoute: '/engineering' },
  { key: 'tasks', label: '任务', title: '任务', icon: ListChecks, component: TasksDockContent, mainRoute: '/tasks' },
  { key: 'legend', label: '图例', title: '图例', icon: Palette, component: LegendDockContent, mainRoute: '/graph' },
  { key: 'thinking', label: '思考流', title: '思考流', icon: BrainCircuit, component: ThinkingDockContent },
  { key: 'heuristics', label: '启发', title: '启发', icon: Lightbulb, component: HeuristicsDockContent },
  { key: 'changelog', label: '变更日志', title: '变更日志', icon: History, component: ChangelogDockContent },
  { key: 'node_detail', label: '节点详情', title: '节点详情', icon: Info, component: NodeDetailDockContent },
];

export const SURFACE_MAP = Object.fromEntries(
  SURFACES.map((s) => [s.key, s])
) as Record<SurfaceKey, SurfaceDef>;

/** 取路由前缀: '/chat/abc' → '/chat' */
export function routePrefix(pathname: string): string {
  const seg = pathname.split('/')[1] ?? '';
  return seg ? `/${seg}` : '/';
}

/** auto(联动)模式的默认配对。修正: 任务页路由是 /tasks(旧 ROUTE_DOCK_MAP 写的 /task-planning 从不命中) */
const ROUTE_PAIR_DEFAULT: { prefix: string; surface: SurfaceKey }[] = [
  { prefix: '/graph', surface: 'legend' },
  { prefix: '/tasks', surface: 'tasks' },
  { prefix: '/engineering', surface: 'engineering' },
  { prefix: '/pipeline', surface: 'context' },
  { prefix: '/chat', surface: 'profile' },
];

export function defaultSurfaceFor(pathname: string): SurfaceKey {
  const p = routePrefix(pathname);
  for (const r of ROUTE_PAIR_DEFAULT) {
    if (r.prefix === p) return r.surface;
  }
  return 'profile';
}

/** 主槽页面的副槽形态(swap 用); 无则该页面不可交换到副槽 */
const ROUTE_SIDE_FORM: { prefix: string; surface: SurfaceKey }[] = [
  { prefix: '/chat', surface: 'chat' },
  { prefix: '/graph', surface: 'legend' },
  { prefix: '/tasks', surface: 'tasks' },
  { prefix: '/engineering', surface: 'engineering' },
  { prefix: '/pipeline', surface: 'context' },
  { prefix: '/profile', surface: 'profile' },
];

export function sideFormForRoute(pathname: string): SurfaceKey | null {
  const p = routePrefix(pathname);
  for (const r of ROUTE_SIDE_FORM) {
    if (r.prefix === p) return r.surface;
  }
  return null;
}

/** 交换目标: 当前 主槽 pathname + 副槽 side 可交换时返回 { navigateTo, newSide }, 否则 null */
export function getSwapTarget(
  pathname: string,
  side: SurfaceKey
): { navigateTo: string; newSide: SurfaceKey } | null {
  const main = SURFACE_MAP[side]?.mainRoute;
  const sideForm = sideFormForRoute(pathname);
  if (!main || !sideForm) return null;
  if (routePrefix(pathname) === main || sideForm === side) return null; // 交换后无变化
  return { navigateTo: main, newSide: sideForm };
}
