import { User, MessageSquare, Braces, GitBranch, ListChecks, Palette, BrainCircuit, Lightbulb, History, Info } from 'lucide-react';
import type { DockContentKey } from '@/stores/uiStore';

/** 内容坞候选内容（共享: 右侧 Dock 头部 + 侧栏中/右选择器 + 中间浮层）
 *  P1-A: 新增 'chat' 对话表面(副槽迷你对话)。 */
export const DOCK_TABS: { key: DockContentKey; label: string; icon: typeof User }[] = [
  { key: 'profile', label: '画像', icon: User },
  { key: 'chat', label: '对话', icon: MessageSquare },
  { key: 'context', label: '上下文', icon: Braces },
  { key: 'engineering', label: '工程链', icon: GitBranch },
  { key: 'tasks', label: '任务', icon: ListChecks },
  { key: 'legend', label: '图例', icon: Palette },
  { key: 'thinking', label: '思考流', icon: BrainCircuit },
  { key: 'heuristics', label: '启发', icon: Lightbulb },
  { key: 'changelog', label: '变更日志', icon: History },
  { key: 'node_detail', label: '节点详情', icon: Info },
];
