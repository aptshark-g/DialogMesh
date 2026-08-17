/** OmniboxPalette — 万能搜索栏面板(P1-C)。
 *
 *  当前真实能力(无后端依赖):
 *   - 页面跳转: 全部路由, 支持中文/英文关键词过滤;
 *   - 操作: 切换主题 / 展开收起副槽;
 *   - ⌘K / Ctrl+K 全局开合, ↑↓ 选择, Enter 执行, Esc 关闭。
 *
 *  待后端(已在 UI_REFACTOR_PLAN 登记):
 *   - B13 内容搜索: 会话历史 / 上下文条目 / 图谱节点统一检索;
 *   - B14 元认知代操作: 自然语言 → 规划 → 经 checkpoint 审批执行。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { specMove } from '@/lib/spec';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Sparkles, LayoutDashboard, MessageSquare, History, ListChecks, GitBranch,
  User, BrainCircuit, Activity, Wrench, Shield, Workflow, Link2, Settings,
  Sun, PanelRight, CornerDownLeft,
} from 'lucide-react';
import { useOmnibox } from '@/stores/omniboxStore';
import { useUIStore } from '@/stores/uiStore';
import { useToggleTheme } from '@/stores/themeStore';
import { cn } from '@/lib/utils';

interface Item {
  id: string;
  group: '页面' | '操作';
  label: string;
  kw: string;
  icon: React.ComponentType<{ className?: string }>;
  run: () => void;
}

export function OmniboxPalette() {
  const open = useOmnibox((s) => s.open);
  const setOpen = useOmnibox((s) => s.setOpen);
  const toggle = useOmnibox((s) => s.toggle);
  const navigate = useNavigate();
  const toggleTheme = useToggleTheme();
  const [query, setQuery] = useState('');
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // 全局热键: ⌘K / Ctrl+K 开合
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [toggle]);

  // 打开时重置并聚焦
  useEffect(() => {
    if (open) {
      setQuery('');
      setCursor(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  const items = useMemo<Item[]>(() => {
    const go = (path: string) => () => { setOpen(false); navigate(path); };
    const pages: Item[] = [
      { id: 'p-dash', group: '页面', label: '总览', kw: 'dashboard overview zonglan', icon: LayoutDashboard, run: go('/') },
      { id: 'p-chat', group: '页面', label: '聊天', kw: 'chat dialog liaotian', icon: MessageSquare, run: go('/chat') },
      { id: 'p-sessions', group: '页面', label: '会话', kw: 'sessions history huihua', icon: History, run: go('/sessions') },
      { id: 'p-tasks', group: '页面', label: '任务', kw: 'tasks planning renwu', icon: ListChecks, run: go('/tasks') },
      { id: 'p-graph', group: '页面', label: '图谱', kw: 'graph tupu', icon: GitBranch, run: go('/graph') },
      { id: 'p-profile', group: '页面', label: '画像', kw: 'profile ocean huaxiang', icon: User, run: go('/profile') },
      { id: 'p-meta', group: '页面', label: '元认知', kw: 'meta cognition yuanrenzhi', icon: BrainCircuit, run: go('/meta') },
      { id: 'p-behavior', group: '页面', label: '行为', kw: 'behavior xingwei', icon: Activity, run: go('/behavior') },
      { id: 'p-eng', group: '页面', label: '工程', kw: 'engineering gongcheng', icon: Wrench, run: go('/engineering') },
      { id: 'p-gateway', group: '页面', label: '网关', kw: 'gateway provider wangguan', icon: Shield, run: go('/gateway') },
      { id: 'p-pipeline', group: '页面', label: '管道', kw: 'pipeline context guandao', icon: Workflow, run: go('/pipeline') },
      { id: 'p-deepchain', group: '页面', label: '深层链', kw: 'deepchain shencenglian', icon: Link2, run: go('/deepchain') },
      { id: 'p-settings', group: '页面', label: '设置', kw: 'settings shezhi', icon: Settings, run: go('/settings') },
    ];
    const actions: Item[] = [
      {
        id: 'a-theme', group: '操作', label: '切换亮色 / 暗色主题', kw: 'theme dark light zhuti', icon: Sun,
        run: () => { toggleTheme(); setOpen(false); },
      },
      {
        id: 'a-dock', group: '操作', label: '展开 / 收起副槽面板', kw: 'dock side panel fuchao mianban', icon: PanelRight,
        run: () => {
          const ui = useUIStore.getState();
          if (ui.sidePanel.isOpen) ui.closeSidePanel();
          else ui.openSidePanel();
          setOpen(false);
        },
      },
    ];
    return [...pages, ...actions];
  }, [navigate, setOpen, toggleTheme]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((it) => it.label.toLowerCase().includes(q) || it.kw.includes(q));
  }, [items, query]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    // stopPropagation: 防止 Esc 冒泡到 SidePanel/CenterDock 的 window 监听把背后的坞一起关掉
    if (e.key === 'Escape') { e.stopPropagation(); setOpen(false); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, filtered.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
    if (e.key === 'Enter' && filtered[cursor]) { e.preventDefault(); filtered[cursor].run(); }
  };

  let lastGroup = '';

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
            className="fixed inset-0 z-50 bg-scrim"
            onClick={() => setOpen(false)}
            role="presentation"
          />
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.99 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            onPointerMove={specMove}
            className="spec-panel fixed left-1/2 top-[18vh] -translate-x-1/2 z-50 w-[min(560px,92vw)] rounded-2xl glass-panel overflow-hidden"
            role="dialog"
            aria-label="万能搜索"
          >
            {/* 输入行 */}
            <div className="flex items-center gap-2.5 px-4 py-3 border-b border-hairline">
              <Sparkles className="w-4 h-4 text-primary shrink-0" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => { setQuery(e.target.value); setCursor(0); }}
                onKeyDown={onKeyDown}
                placeholder="搜索页面与操作 — 内容搜索 / 元认知代操作在路上"
                aria-label="万能搜索输入"
                className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
              />
              <kbd className="text-[10px] text-text-muted border border-subtle rounded px-1.5 py-0.5">Esc</kbd>
            </div>

            {/* 结果列表 */}
            <div className="max-h-[46vh] overflow-y-auto py-1.5">
              {filtered.map((it, i) => {
                const Icon = it.icon;
                const head = it.group !== lastGroup ? it.group : null;
                lastGroup = it.group;
                return (
                  <div key={it.id}>
                    {head && (
                      <div className="px-4 pt-2 pb-1 text-[10px] font-medium text-text-muted">{head}</div>
                    )}
                    <button
                      type="button"
                      onMouseEnter={() => setCursor(i)}
                      onClick={it.run}
                      className={cn(
                        'w-full flex items-center gap-2.5 px-4 py-2 text-left text-sm transition-colors',
                        i === cursor ? 'bg-primary/10 text-text-primary' : 'text-text-secondary'
                      )}
                    >
                      <Icon className={cn('w-4 h-4 shrink-0', i === cursor ? 'text-primary' : 'text-text-muted')} />
                      <span className="flex-1 truncate">{it.label}</span>
                      {i === cursor && <CornerDownLeft className="w-3.5 h-3.5 text-text-muted shrink-0" />}
                    </button>
                  </div>
                );
              })}
              {filtered.length === 0 && (
                <div className="px-4 py-8 text-center">
                  <p className="text-xs text-text-muted">无匹配页面 / 操作</p>
                  <p className="text-[11px] text-text-muted mt-1.5 leading-relaxed">
                    「{query}」的内容搜索(会话 · 上下文 · 图谱)待后端统一检索接口
                  </p>
                </div>
              )}
            </div>

            {/* 底注 */}
            <div className="px-4 py-2 border-t border-hairline text-[10px] text-text-muted">
              ↑↓ 选择 · Enter 打开 · Ctrl K 开合
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
