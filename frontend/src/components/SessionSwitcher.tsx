// FILE: src/components/SessionSwitcher.tsx
// P3 会话切换器:顶栏标题下拉 = 按项目分组的会话列表(替换原死按钮)
// 数据源:useV6Sessions(v6 会话文件)+ projectStore(项目分组)+ chatStore(当前会话)

import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Check, ChevronDown, MessageSquare, Plus, Search } from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import { useProjectStore } from '@/stores/projectStore';
import { useV6Sessions } from '@/hooks/useV6Sessions';
import { cn } from '@/lib/utils';
import { specMove } from '@/lib/spec';

/** v6 会话文件名可能带 .json 后缀,聊天路由/store 用裸 id */
const stripExt = (name: string) => name.replace(/\.json$/, '');
const shortId = (id: string) => (id.length > 13 ? `${id.slice(0, 13)}…` : id);

interface SessionSwitcherProps {
  /** 非聊天页时显示的兜底标题 */
  fallbackTitle: string;
}

export function SessionSwitcher({ fallbackTitle }: SessionSwitcherProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const onChat = location.pathname.startsWith('/chat');
  const sessionId = useChatStore((s) => s.sessionId);

  const projects = useProjectStore((s) => s.projects);
  const sessionProject = useProjectStore((s) => s.sessionProject);
  const { sessions, refresh } = useV6Sessions();

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);

  // 打开时刷新列表 + 重置过滤;Esc / 点外关闭
  useEffect(() => {
    if (!open) return;
    refresh();
    setQuery('');
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onDown);
    };
  }, [open, refresh]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? sessions.filter((s) => s.name.toLowerCase().includes(q)) : sessions;
  }, [sessions, query]);

  /** 分组:有会话的项目在前(按侧栏顺序),未分配兜底 */
  const groups = useMemo(() => {
    const list: { key: string; label: string; color: string | null; items: typeof filtered }[] = [];
    for (const p of projects) {
      const items = filtered.filter((s) => sessionProject[s.name] === p.id);
      if (items.length) list.push({ key: p.id, label: p.name, color: p.color, items });
    }
    const rest = filtered.filter((s) => {
      const pid = sessionProject[s.name];
      return !pid || !projects.some((p) => p.id === pid);
    });
    if (rest.length) list.push({ key: '__rest', label: '未分配', color: null, items: rest });
    return list;
  }, [filtered, projects, sessionProject]);

  // 当前会话的项目徽(sessionProject 的键是文件名,可能带 .json)
  const activeProject =
    onChat && sessionId
      ? projects.find(
          (p) => p.id === (sessionProject[sessionId] ?? sessionProject[`${sessionId}.json`])
        ) ?? null
      : null;
  const title = onChat && sessionId ? `会话 ${shortId(sessionId)}` : fallbackTitle;

  return (
    <div ref={rootRef} className="relative flex items-center gap-2 min-w-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="切换会话"
        aria-expanded={open}
        className="flex items-center gap-1.5 text-[15px] font-semibold text-text-primary hover:text-primary transition-colors"
      >
        {activeProject && (
          <span className="w-2 h-2 rounded-[3px] shrink-0" style={{ background: activeProject.color }} />
        )}
        <span className="truncate">{title}</span>
        <ChevronDown
          className={cn('w-4 h-4 text-text-muted shrink-0 transition-transform', open && 'rotate-180')}
        />
      </button>

      {open && (
        <div onPointerMove={specMove}
          className="spec-panel absolute left-0 top-9 z-dropdown w-72 rounded-2xl glass-panel overflow-hidden">
          {/* 过滤 */}
          <div className="p-2 border-b border-hairline">
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-wash">
              <Search className="w-3.5 h-3.5 text-text-muted shrink-0" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="过滤会话…"
                aria-label="过滤会话"
                className="w-full bg-transparent text-xs text-text-primary placeholder:text-text-muted focus:outline-none"
              />
            </div>
          </div>

          <div className="max-h-[380px] overflow-y-auto py-1">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                navigate('/chat/new');
              }}
              className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs text-primary hover:bg-wash transition-colors"
            >
              <Plus className="w-3.5 h-3.5 shrink-0" />
              新会话
            </button>

            {groups.map((g) => (
              <div key={g.key}>
                <div className="px-3 pt-2 pb-1 flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.1em] text-text-muted">
                  {g.color && (
                    <span className="w-2 h-2 rounded-[3px] shrink-0" style={{ background: g.color }} />
                  )}
                  {g.label}
                  <span className="font-normal">{g.items.length}</span>
                </div>
                {g.items.map((s) => {
                  const sid = stripExt(s.name);
                  const isCurrent = onChat && sid === sessionId;
                  return (
                    <button
                      key={s.name}
                      type="button"
                      onClick={() => {
                        setOpen(false);
                        navigate(`/chat/${sid}`);
                      }}
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-wash transition-colors group"
                    >
                      <MessageSquare className="w-3.5 h-3.5 text-text-muted shrink-0" />
                      <span
                        className={cn(
                          'truncate font-mono',
                          isCurrent ? 'text-primary' : 'text-text-secondary group-hover:text-text-primary'
                        )}
                      >
                        {shortId(sid)}
                      </span>
                      {isCurrent && <Check className="w-3.5 h-3.5 text-primary ml-auto shrink-0" />}
                    </button>
                  );
                })}
              </div>
            ))}

            {groups.length === 0 && (
              <div className="px-3 py-6 text-center text-xs text-text-muted">无匹配会话</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
