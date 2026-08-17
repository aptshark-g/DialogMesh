import { useCallback, useState } from 'react';
import type { ComponentType } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  MessageSquare,
  Network,
  UserCircle,
  CheckSquare,
  Settings,
  Menu,
  X,
  Zap,
  Plus,
  Shield,
  Workflow,
  GitBranch,
  LayoutDashboard,
  History,
  Brain,
  Radar,
  Wrench,
  MoreHorizontal,
  Pencil,
  Trash2,
  FolderPlus,
  FolderOpen,
  ChevronRight,
} from 'lucide-react';
import { useHealth } from '../hooks/useHealth.ts';
import { useProjectStore, PROJECT_PALETTE } from '../stores/projectStore.ts';
import { useUIStore } from '../stores/uiStore.ts';
import { browseProjectDirs, type V6ProjectBrowseEntry } from '../api/v6';
import { Modal } from './ui/Modal';

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}

interface NavGroupPages {
  label: string;
  type: 'pages';
  items: NavItem[];
}
interface NavGroupProjects {
  label: string;
  type: 'projects';
}
type NavGroup = NavGroupPages | NavGroupProjects;


const navGroups: NavGroup[] = [
  {
    label: '主导航',
    type: 'pages',
    items: [
      { to: '/', label: '总览', icon: LayoutDashboard },
      { to: '/chat', label: '聊天', icon: MessageSquare },
      { to: '/sessions', label: '会话', icon: History },
      { to: '/tasks', label: '任务', icon: CheckSquare },
    ],
  },
  { label: '项目', type: 'projects' },
  {
    label: '洞察',
    type: 'pages',
    items: [
      { to: '/graph', label: '图谱', icon: Network },
      { to: '/profile', label: '画像', icon: UserCircle },
      { to: '/meta', label: '元认知', icon: Brain },
      { to: '/behavior', label: '行为', icon: Radar },
    ],
  },
  {
    label: '工程',
    type: 'pages',
    items: [
      { to: '/engineering', label: '工程', icon: Wrench },
      { to: '/gateway', label: '网关', icon: Shield },
      { to: '/pipeline', label: '管道', icon: Workflow },
      { to: '/deepchain', label: '深层链', icon: GitBranch },
    ],
  },
  {
    label: '系统',
    type: 'pages',
    items: [{ to: '/settings', label: '设置', icon: Settings }],
  },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  // P2 项目范围:全局 store(localStorage 持久化);激活项目 = 会话列表过滤范围
  const projects = useProjectStore((s) => s.projects);
  const activeProject = useProjectStore((s) => s.activeProjectId);
  const setActiveProject = useProjectStore((s) => s.setActiveProject);
  const createProject = useProjectStore((s) => s.createProject);
  const renameProject = useProjectStore((s) => s.renameProject);
  const deleteProject = useProjectStore((s) => s.deleteProject);
  const recolorProject = useProjectStore((s) => s.recolorProject);
  const setProjectPath = useProjectStore((s) => s.setProjectPath);
  // P1-H: 侧栏可拖拽宽度(持久化) + 拖拽中禁过渡
  const sidebarWidth = useUIStore((s) => s.sidebarWidth);
  const [resizing, setResizing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState('');
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  // 2026-08-17: 创建项目后选择工作区文件夹（新建/已有）
  const [folderFor, setFolderFor] = useState<string | null>(null);
  const [folderForName, setFolderForName] = useState('');
  const [folderMode, setFolderMode] = useState<'new' | 'existing'>('new');
  const [folderPath, setFolderPath] = useState('');
  const [browsePath, setBrowsePath] = useState('');
  const [browseEntries, setBrowseEntries] = useState<V6ProjectBrowseEntry[]>([]);
  const [browseLoading, setBrowseLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { health, error } = useHealth();

  const isOnline = health !== null && error === null;

  const checkIsActive = (to: string) => {
    if (location.pathname === to) return true;
    // Special handling for chat routes with dynamic session IDs
    if (to === '/chat' && location.pathname.startsWith('/chat')) return true;
    return false;
  };

  const slug = (name: string, id: string) => {
    const safe = name.trim().toLowerCase().replace(/[^\w\u4e00-\u9fa5-]+/g, '-').replace(/^-+|-+$/g, '');
    return `${safe || 'project'}-${id.slice(0, 6)}`;
  };

  const loadBrowse = useCallback(async (dir: string) => {
    setBrowseLoading(true);
    try {
      const r = await browseProjectDirs(dir || undefined);
      setBrowsePath(r.path);
      setBrowseEntries(r.entries);
    } catch {
      setBrowseEntries([]);
    } finally {
      setBrowseLoading(false);
    }
  }, []);

  const openFolderPicker = (p: { id: string; name: string }) => {
    setFolderFor(p.id);
    setFolderForName(p.name);
    setFolderMode('new');
    setFolderPath(`data/projects/${slug(p.name, p.id)}`);
    loadBrowse('');
  };

  const confirmFolder = () => {
    if (folderFor && folderPath.trim()) {
      setProjectPath(folderFor, folderPath.trim(), folderMode === 'new');
    }
    setFolderFor(null);
    navigate('/sessions');
  };

  const skipFolder = () => {
    setFolderFor(null);
    navigate('/sessions');
  };

  // P1-H: 指针镜面高光(liquid glass specular) — 指针位置写入 CSS 变量
  const onSpecMove = (e: React.PointerEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty('--mx', `${e.clientX - r.left}px`);
    e.currentTarget.style.setProperty('--my', `${e.clientY - r.top}px`);
  };
  // P1-H: 侧栏拖拽调宽(桌面端, 180-320)
  const onSidebarResizeStart = (e: React.PointerEvent) => {
    e.preventDefault();
    setResizing(true);
    const startX = e.clientX;
    const startWidth = useUIStore.getState().sidebarWidth;
    const onMove = (ev: PointerEvent) => {
      useUIStore.getState().setSidebarWidth(startWidth + (ev.clientX - startX));
    };
    const onUp = () => {
      setResizing(false);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  return (
    <>
      {/* Mobile Toggle */}
      <button
        type="button"
        onClick={() => setMobileOpen((v) => !v)}
        className="fixed top-4 left-4 z-50 p-2 rounded-lg bg-surface-card shadow-md border border-subtle lg:hidden"
        aria-label={mobileOpen ? '关闭菜单' : '打开菜单'}
      >
        {mobileOpen ? (
          <X className="w-5 h-5 text-primary" />
        ) : (
          <Menu className="w-5 h-5 text-primary" />
        )}
      </button>

      {/* Mobile Overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-30 lg:hidden"
            onClick={() => setMobileOpen(false)}
            role="presentation"
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <motion.aside
        initial={false}
        animate={{
          x: mobileOpen ? 0 : undefined,
        }}
        style={{ width: collapsed ? undefined : sidebarWidth }}
        className={[
          'fixed lg:static inset-y-0 left-0 z-40',
          'bg-glass-strong backdrop-blur-xl backdrop-saturate-150 edge-fade-r',
          resizing ? 'flex flex-col transition-none' : 'flex flex-col transition-all duration-300',
          collapsed ? 'w-16' : '',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        ].join(' ')}
      >
        {/* Logo */}
        <div className="h-[52px] flex items-center px-3 shrink-0">
          <motion.div
            className="w-5 h-5 flex items-center justify-center text-sm shrink-0 cursor-pointer"
            aria-hidden="true"
            whileHover={{ rotate: 15, scale: 1.1 }}
            transition={{ type: 'spring', stiffness: 300, damping: 20 }}
          >
            🔶
          </motion.div>
          <AnimatePresence>
            {!collapsed && (
              <motion.div
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.2 }}
                className="ml-2 flex items-baseline gap-1.5 overflow-hidden"
              >
                <span className="font-semibold text-primary text-[14px] truncate">
                  DialogMesh
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* New Session Quick Action */}
        <div className="px-2.5 pt-2 shrink-0">
          <NavLink
            to="/chat/new"
            onClick={() => setMobileOpen(false)}
            className={[
              'flex items-center justify-center px-3 py-2 rounded-full transition-colors',
              'bg-primary text-white shadow-sm',
              'text-[13px] font-medium hover:bg-primary-dark',
            ].join(' ')}
            title={collapsed ? '新会话' : undefined}
          >
            <Plus className="w-3.5 h-3.5 shrink-0" />
            {!collapsed && <span className="ml-2">新会话</span>}
          </NavLink>
        </div>

        {/* Nav:分组渲染;页面位置激活 = 左橙条,项目范围激活 = 右琥珀点 */}
        <nav className="flex-1 overflow-y-auto py-2 px-2" onMouseLeave={() => setHoverKey(null)}>
          {navGroups.map((group) => (
            <div key={group.label} className="mb-4">
              {!collapsed && (
                <div className="flex items-center px-2.5 pb-1.5">
                  <span className="text-[10px] font-semibold tracking-[0.12em] text-text-muted">
                    {group.label}
                  </span>
                  {group.type === 'projects' && (
                    <button
                      type="button"
                      onClick={() => setCreating(true)}
                      className="ml-auto p-0.5 rounded text-text-muted hover:text-text-primary hover:bg-wash transition-colors"
                      title="新建项目"
                      aria-label="新建项目"
                    >
                      <Plus className="w-3 h-3" />
                    </button>
                  )}
                </div>
              )}
              {group.type === 'projects' ? (
                <div className="space-y-1">
                  {menuFor && (
                    <div className="fixed inset-0 z-10" onClick={() => setMenuFor(null)} aria-hidden="true" />
                  )}
                  {creating && !collapsed && (
                    <div className="px-1 pb-1">
                      <input
                        autoFocus
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            const name = draft.trim();
                            if (name) {
                              const p = createProject(name);
                              setActiveProject(p.id);
                              // 2026-08-17: 创建后先选工作区文件夹（新建/已有）,
                              // 确认或跳过后再进入会话页
                              openFolderPicker(p);
                            }
                            setDraft('');
                            setCreating(false);
                          }
                          if (e.key === 'Escape') {
                            setDraft('');
                            setCreating(false);
                          }
                        }}
                        onBlur={() => {
                          setDraft('');
                          setCreating(false);
                        }}
                        placeholder="项目名称…"
                        aria-label="新建项目名称"
                        className="w-full bg-wash rounded-md px-2.5 py-1.5 text-[13px] text-text-primary placeholder:text-text-muted focus:outline-none"
                      />
                    </div>
                  )}
                  {projects.length === 0 && !creating && !collapsed && (
                    <div className="px-3 py-1.5 text-[11px] text-text-muted">暂无项目</div>
                  )}
                  {projects.map((p) => {
                    const isScope = activeProject === p.id;
                    return (
                      <div key={p.id} className="relative">
                        {renamingId === p.id && !collapsed ? (
                          <input
                            autoFocus
                            defaultValue={p.name}
                            aria-label={`重命名项目 ${p.name}`}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                const name = e.currentTarget.value.trim();
                                if (name) renameProject(p.id, name);
                                setRenamingId(null);
                              }
                              if (e.key === 'Escape') setRenamingId(null);
                            }}
                            onBlur={() => setRenamingId(null)}
                            className="w-full bg-wash rounded-md px-2.5 py-1.5 text-[13px] text-text-primary focus:outline-none"
                          />
                        ) : (
                          <button
                            type="button"
                            onClick={() => {
                              const next = activeProject === p.id ? null : p.id;
                              setActiveProject(next);
                              if (next) navigate(`/projects/${p.id}`);
                              setMobileOpen(false);
                            }}
                            onMouseEnter={() => setHoverKey(`proj:${p.id}`)}
                            onPointerMove={onSpecMove}
                            onContextMenu={(e) => {
                              e.preventDefault();
                              if (!collapsed) setMenuFor(p.id);
                            }}
                            className={[
                              'spec-item',
                              'relative w-full flex items-center px-2.5 py-1.5 rounded-md transition-colors',
                              'text-[13px] group',
                              isScope
                                ? 'bg-wash text-text-primary font-medium'
                                : 'text-text-secondary hover:text-text-primary',
                            ].join(' ')}
                            title={collapsed ? p.name : undefined}
                          >
                            {!isScope && hoverKey === `proj:${p.id}` && (
                              <motion.span
                                layoutId="nav-hover-pill"
                                className="absolute inset-0 rounded-md bg-wash pointer-events-none"
                                transition={{ type: 'spring', stiffness: 680, damping: 45 }}
                              />
                            )}
                            <span
                              className="w-[15px] h-[15px] rounded-[5px] shrink-0 flex items-center justify-center text-[9px] font-bold text-white"
                              style={{ background: p.color }}
                            >
                              {p.name.slice(0, 1).toUpperCase()}
                            </span>
                            {!collapsed && (
                              <>
                                <span className="ml-3 truncate flex-1 text-left">{p.name}</span>
                                {isScope && (
                                  <span className="w-[5px] h-[5px] rounded-full bg-primary shrink-0" />
                                )}
                                <span
                                  role="button"
                                  aria-label={`项目 ${p.name} 更多操作`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setMenuFor(menuFor === p.id ? null : p.id);
                                  }}
                                  className="ml-1 p-0.5 rounded text-text-muted opacity-0 group-hover:opacity-100 hover:text-text-primary transition-opacity shrink-0"
                                >
                                  <MoreHorizontal className="w-3.5 h-3.5" />
                                </span>
                              </>
                            )}
                          </button>
                        )}
                        {menuFor === p.id && (
                          <div onPointerMove={onSpecMove}
                          className="spec-panel absolute left-2 right-1 top-8 z-dropdown rounded-xl glass-panel overflow-hidden">
                            <button
                              type="button"
                              onClick={() => { setRenamingId(p.id); setMenuFor(null); }}
                              className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs text-text-secondary hover:bg-wash hover:text-text-primary transition-colors"
                            >
                              <Pencil className="w-3.5 h-3.5" /> 重命名
                            </button>
                            <div className="flex items-center gap-1.5 px-3 py-2.5 border-t border-hairline">
                              {PROJECT_PALETTE.map((c) => (
                                <button
                                  key={c}
                                  type="button"
                                  aria-label={`项目色 ${c}`}
                                  onClick={() => { recolorProject(p.id, c); setMenuFor(null); }}
                                  className="w-4 h-4 rounded-[5px] transition-transform hover:scale-110"
                                  style={{ background: c }}
                                />
                              ))}
                            </div>
                            <button
                              type="button"
                              onClick={() => { deleteProject(p.id); setMenuFor(null); }}
                              className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs text-status-error hover:bg-wash transition-colors border-t border-hairline"
                            >
                              <Trash2 className="w-3.5 h-3.5" /> 删除项目
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="space-y-1">
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const isActive = checkIsActive(item.to);
                    return (
                      <motion.div
                        key={item.to}
                        whileTap={{ scale: 0.98 }}
                        transition={{ duration: 0.15 }}
                        onHoverStart={() => setHoverKey(item.to)}
                      >
                        <NavLink
                          to={item.to}
                          onClick={() => setMobileOpen(false)}
                          onPointerMove={onSpecMove}
                          className={[
                            'spec-item',
                            'relative flex items-center px-2.5 py-1.5 rounded-md transition-colors',
                            'text-[13px]',
                            isActive
                              ? 'bg-wash text-text-primary font-medium'
                              : 'text-text-secondary hover:text-text-primary',
                          ].join(' ')}
                          title={collapsed ? item.label : undefined}
                        >
                          {isActive && (
                            <span className="absolute left-0 top-1/2 -translate-y-1/2 h-3/5 w-[3px] rounded-full bg-primary" />
                          )}
                          {!isActive && hoverKey === item.to && (
                            <motion.span
                              layoutId="nav-hover-pill"
                              className="absolute inset-0 rounded-md bg-wash pointer-events-none"
                              transition={{ type: 'spring', stiffness: 680, damping: 45 }}
                            />
                          )}
                          <Icon
                            className={[
                              'w-[15px] h-[15px] shrink-0',
                              isActive ? 'text-primary' : 'text-text-muted',
                            ].join(' ')}
                          />
                          {!collapsed && (
                            <motion.span
                              initial={{ opacity: 0 }}
                              animate={{ opacity: 1 }}
                              transition={{ delay: 0.1 }}
                              className="ml-3 truncate"
                            >
                              {item.label}
                            </motion.span>
                          )}
                        </NavLink>
                      </motion.div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </nav>


        {/* Bottom: Health & Collapse(状态点化,去卡片去顶线) */}
        <div className="p-3 pt-1 space-y-1 shrink-0">
          {/* Health Status:6px 状态点 + muted 文案 */}
          <div
            className="flex items-center gap-2 px-2.5 py-1"
            title={isOnline ? '后端服务正常' : '后端服务异常'}
          >
            <motion.span
              animate={isOnline ? { scale: [1, 1.25, 1] } : {}}
              transition={{ duration: 2, repeat: Infinity }}
              className={[
                'w-1.5 h-1.5 rounded-full shrink-0',
                isOnline ? 'bg-status-success' : 'bg-status-error',
              ].join(' ')}
            />
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.1 }}
                className="text-[11px] text-text-muted truncate"
              >
                {isOnline ? 'Backend Online' : 'Backend Offline'}
              </motion.span>
            )}
          </div>

          {/* Collapse Toggle (desktop only) */}
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            className={[
              'hidden lg:flex items-center px-2.5 py-1.5 rounded-lg',
              'text-text-muted hover:text-primary hover:bg-surface-card-hover',
              'text-xs transition-colors w-full',
            ].join(' ')}
            aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
            aria-expanded={!collapsed}
          >
            <Zap className="w-4 h-4 shrink-0" />
            <AnimatePresence>
              {!collapsed && (
                <motion.span
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: 'auto' }}
                  exit={{ opacity: 0, width: 0 }}
                  transition={{ duration: 0.15 }}
                  className="ml-2 overflow-hidden whitespace-nowrap"
                >
                  收起
                </motion.span>
              )}
            </AnimatePresence>
          </button>
        </div>
        {/* P1-H: 拖拽调宽手柄(桌面端, 收起时隐藏) */}
        {!collapsed && (
          <div
            onPointerDown={onSidebarResizeStart}
            className="group absolute -right-1.5 top-0 bottom-0 w-3 cursor-col-resize hidden lg:block z-20"
            aria-label="调整侧栏宽度"
          >
            <div className="ml-auto h-full w-1 rounded-full group-hover:bg-primary/30 group-active:bg-primary/40 transition-colors" />
          </div>
        )}
      </motion.aside>

      {/* 2026-08-17: 创建项目后选择工作区文件夹（新建/已有） */}
      <Modal
        isOpen={folderFor !== null}
        onClose={skipFolder}
        title={`选择项目文件夹「${folderForName}」`}
        footer={
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={skipFolder}
              className="px-3 py-1.5 rounded-lg border border-subtle text-xs text-text-secondary hover:text-text-primary transition-colors"
            >
              暂不关联
            </button>
            <button
              type="button"
              onClick={confirmFolder}
              disabled={!folderPath.trim()}
              className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-40"
            >
              确认关联
            </button>
          </div>
        }
      >
        <div className="space-y-3">
          <div className="flex gap-2">
            {(
              [
                ['new', '新建文件夹', FolderPlus],
                ['existing', '已有文件夹', FolderOpen],
              ] as const
            ).map(([mode, label, Icon]) => (
              <button
                key={mode}
                type="button"
                onClick={() => {
                  setFolderMode(mode);
                  if (mode === 'new' && folderFor) {
                    const p = projects.find((x) => x.id === folderFor);
                    setFolderPath(`data/projects/${slug(p?.name || folderForName, folderFor)}`);
                  } else {
                    loadBrowse(browsePath || '');
                  }
                }}
                className={[
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
                  folderMode === mode
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-subtle text-text-secondary hover:text-primary',
                ].join(' ')}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </button>
            ))}
          </div>

          {folderMode === 'new' ? (
            <div className="rounded-lg border border-subtle p-3 space-y-2">
              <p className="text-xs text-text-secondary">
                将自动在项目工作区 <span className="font-mono text-text-primary">data/projects/</span>
                下创建目录（可修改路径）。
              </p>
              <input
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                aria-label="新建文件夹路径"
                className="w-full bg-wash rounded-lg px-3 py-2 text-xs font-mono text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
              />
            </div>
          ) : (
            <div className="rounded-lg border border-subtle overflow-hidden">
              <div className="flex items-center justify-between px-3 py-2 bg-wash text-xs">
                <span className="font-mono text-text-secondary truncate">{browsePath || '加载中…'}</span>
                <button
                  type="button"
                  onClick={() => {
                    const parent = browsePath.replace(/[\\/]+$/, '').split(/[\\/]/).slice(0, -1).join('\\');
                    if (parent) loadBrowse(parent);
                  }}
                  className="text-text-secondary hover:text-primary shrink-0 ml-2"
                >
                  上一级
                </button>
              </div>
              <div className="max-h-44 overflow-y-auto divide-y divide-border-subtle">
                {browseLoading ? (
                  <div className="px-3 py-4 text-xs text-text-muted text-center">加载目录…</div>
                ) : browseEntries.length === 0 ? (
                  <div className="px-3 py-4 text-xs text-text-muted text-center">此目录下暂无子文件夹</div>
                ) : (
                  browseEntries.map((e) => (
                    <div
                      key={e.path}
                      role="button"
                      tabIndex={0}
                      onClick={() => setFolderPath(e.path)}
                      onKeyDown={(ev) => { if (ev.key === 'Enter') setFolderPath(e.path); }}
                      className={[
                        'flex items-center gap-2 px-3 py-2 text-xs transition-colors cursor-pointer',
                        folderPath === e.path ? 'bg-primary/5 text-primary' : 'text-text-secondary hover:bg-surface-card-hover',
                      ].join(' ')}
                    >
                      <FolderOpen className="w-3.5 h-3.5 shrink-0" />
                      <span className="truncate flex-1">{e.name}</span>
                      <button
                        type="button"
                        onClick={(ev) => { ev.stopPropagation(); loadBrowse(e.path); }}
                        aria-label={`进入 ${e.name}`}
                        className="p-0.5 rounded hover:text-primary shrink-0"
                      >
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))
                )}
              </div>
              <div className="px-3 py-2 border-t border-border-subtle">
                <input
                  value={folderPath}
                  onChange={(e) => setFolderPath(e.target.value)}
                  placeholder="或手动输入文件夹路径…"
                  aria-label="已有文件夹路径"
                  className="w-full bg-wash rounded-lg px-3 py-2 text-xs font-mono text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40"
                />
              </div>
            </div>
          )}

          <p className="text-[11px] text-text-muted">
            项目=工作区: 该项目下的会话将归入此文件夹, 便于后续以项目为单位做经验总结与分支管理。
          </p>
        </div>
      </Modal>
    </>
  );
}
