import { useState } from 'react';
import type { ComponentType } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
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
} from 'lucide-react';
import { useHealth } from '../hooks/useHealth.ts';
import { DockPicker } from './dock/DockPicker';

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

interface ProjectItem {
  id: string;
  name: string;
  color: string;
  fg: string;
  initial: string;
}

// P0 假数据(P2 接入真实映射,见 UI_REFACTOR_PLAN B1)
const demoProjects: ProjectItem[] = [
  { id: 'vibration', name: '毕设 · 主动振动控制', color: 'var(--color-amber)', fg: '#17130B', initial: '振' },
  { id: 'memorygraph', name: 'memorygraph', color: '#7C8CFF', fg: '#FFFFFF', initial: 'M' },
  { id: 'paper', name: '学报投稿 · 端云蒸馏', color: 'var(--status-success)', fg: '#FFFFFF', initial: '投' },
];

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
  // P0 项目范围(本地态;P2 迁入全局 store 并接真实数据,见 UI_REFACTOR_PLAN B1)
  const [activeProject, setActiveProject] = useState('vibration');
  const location = useLocation();
  const { health, error } = useHealth();

  const isOnline = health !== null && error === null;

  const checkIsActive = (to: string) => {
    if (location.pathname === to) return true;
    // Special handling for chat routes with dynamic session IDs
    if (to === '/chat' && location.pathname.startsWith('/chat')) return true;
    return false;
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
        className={[
          'fixed lg:static inset-y-0 left-0 z-40',
          'bg-surface-sidebar',
          'flex flex-col transition-all duration-300',
          collapsed ? 'w-16' : 'w-64',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        ].join(' ')}
      >
        {/* Logo */}
        <div className="h-16 flex items-center px-4 shrink-0">
          <motion.div
            className="w-7 h-7 flex items-center justify-center text-lg shrink-0 cursor-pointer"
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
                className="ml-3 flex items-baseline gap-2 overflow-hidden"
              >
                <span className="font-semibold text-primary text-lg truncate">
                  DialogMesh
                </span>
                <span className="text-xs text-text-muted">v6.0</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* New Session Quick Action */}
        <div className="px-3 pt-3 shrink-0">
          <NavLink
            to="/chat/default"
            onClick={() => setMobileOpen(false)}
            className={[
              'flex items-center justify-center px-3 py-2.5 rounded-lg transition-colors',
              'bg-primary/10 border border-primary/20 text-primary',
              'text-sm font-medium hover:bg-primary/20',
            ].join(' ')}
            title={collapsed ? '新会话' : undefined}
          >
            <Plus className="w-4 h-4 shrink-0" />
            {!collapsed && <span className="ml-2">新会话</span>}
          </NavLink>
        </div>

        {/* Nav:分组渲染;页面位置激活 = 左橙条,项目范围激活 = 右琥珀点 */}
        <nav className="flex-1 overflow-y-auto py-3 px-2">
          {navGroups.map((group) => (
            <div key={group.label} className="mb-5">
              {!collapsed && (
                <div className="flex items-center px-3 pb-1.5">
                  <span className="text-[10px] font-semibold tracking-[0.12em] text-text-muted">
                    {group.label}
                  </span>
                  {group.type === 'projects' && (
                    <button
                      type="button"
                      className="ml-auto p-0.5 rounded text-text-muted hover:text-text-primary hover:bg-surface-card-hover transition-colors"
                      title="新建项目(P2 接入数据)"
                    >
                      <Plus className="w-3 h-3" />
                    </button>
                  )}
                </div>
              )}
              {group.type === 'projects' ? (
                <div className="space-y-1">
                  {demoProjects.map((p) => {
                    const isScope = activeProject === p.id;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => setActiveProject(p.id)}
                        className={[
                          'w-full flex items-center px-3 py-2 rounded-lg transition-colors',
                          'text-sm',
                          isScope
                            ? 'bg-surface-card text-text-primary font-medium'
                            : 'text-text-secondary hover:bg-surface-card-hover hover:text-text-primary',
                        ].join(' ')}
                        title={collapsed ? p.name : undefined}
                      >
                        <span
                          className="w-[15px] h-[15px] rounded-[5px] shrink-0 flex items-center justify-center text-[9px] font-bold"
                          style={{ background: p.color, color: p.fg }}
                        >
                          {p.initial}
                        </span>
                        {!collapsed && (
                          <>
                            <span className="ml-3 truncate flex-1 text-left">{p.name}</span>
                            {isScope && (
                              <span className="w-[5px] h-[5px] rounded-full bg-primary shrink-0" />
                            )}
                          </>
                        )}
                      </button>
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
                      >
                        <NavLink
                          to={item.to}
                          onClick={() => setMobileOpen(false)}
                          className={[
                            'relative flex items-center px-3 py-2 rounded-lg transition-colors',
                            'text-sm',
                            isActive
                              ? 'bg-surface-card text-text-primary font-medium'
                              : 'text-text-secondary hover:bg-surface-card-hover hover:text-text-primary',
                          ].join(' ')}
                          title={collapsed ? item.label : undefined}
                        >
                          {isActive && (
                            <span className="absolute left-0 top-1/2 -translate-y-1/2 h-3/5 w-[3px] rounded-full bg-primary" />
                          )}
                          <Icon
                            className={[
                              'w-[17px] h-[17px] shrink-0',
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

        {/* 内容坞选择器 — 中间/右边显示（B5） */}
        <DockPicker />

        {/* Bottom: Health & Collapse(状态点化,去卡片去顶线) */}
        <div className="p-3 pt-1 space-y-1 shrink-0">
          {/* Health Status:6px 状态点 + muted 文案 */}
          <div
            className="flex items-center gap-2 px-3 py-1.5"
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
              'hidden lg:flex items-center px-3 py-2 rounded-lg',
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
      </motion.aside>
    </>
  );
}
