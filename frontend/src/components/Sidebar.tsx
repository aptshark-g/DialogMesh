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
  Activity,
  Zap,
  Plus,
} from 'lucide-react';
import { useHealth } from '../hooks/useHealth.ts';

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}

const navItems: NavItem[] = [
  { to: '/chat/default', label: '聊天', icon: MessageSquare },
  { to: '/graph', label: '图谱', icon: Network },
  { to: '/profile', label: '画像', icon: UserCircle },
  { to: '/tasks', label: '任务', icon: CheckSquare },
  { to: '/settings', label: '设置', icon: Settings },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const { health, error } = useHealth();

  const isOnline = health !== null && error === null;

  const checkIsActive = (to: string) => {
    if (location.pathname === to) return true;
    // Special handling for chat routes with dynamic session IDs
    if (to === '/chat/default' && location.pathname.startsWith('/chat/')) return true;
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
          'bg-surface-sidebar border-r border-subtle',
          'flex flex-col transition-all duration-300',
          collapsed ? 'w-16' : 'w-64',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        ].join(' ')}
      >
        {/* Logo */}
        <div className="h-16 flex items-center px-4 border-b border-subtle shrink-0">
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
                <span className="text-xs text-text-muted">v3.0</span>
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

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = checkIsActive(item.to);
            return (
              <motion.div
                key={item.to}
                whileHover={{ x: 2 }}
                whileTap={{ scale: 0.98 }}
                transition={{ duration: 0.15 }}
              >
                <NavLink
                  to={item.to}
                  onClick={() => setMobileOpen(false)}
                  className={[
                    'flex items-center px-3 py-2.5 rounded-lg transition-colors',
                    'text-sm font-medium',
                    isActive
                      ? 'bg-surface-card text-primary ring-1 ring-primary/20'
                      : 'text-text-secondary hover:bg-surface-card-hover hover:text-primary',
                  ].join(' ')}
                  title={collapsed ? item.label : undefined}
                >
                  <Icon
                    className={[
                      'w-5 h-5 shrink-0',
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
        </nav>

        {/* Bottom: Health & Collapse */}
        <div className="border-t border-subtle p-3 space-y-2 shrink-0">
          {/* Health Status */}
          <div
            className={[
              'flex items-center px-3 py-2 rounded-lg',
              'bg-surface-card border border-subtle',
            ].join(' ')}
            title={isOnline ? '后端服务正常' : '后端服务异常'}
          >
            <motion.div
              animate={isOnline ? { scale: [1, 1.15, 1] } : {}}
              transition={{ duration: 2, repeat: Infinity }}
            >
              <Activity
                className={[
                  'w-4 h-4 shrink-0',
                  isOnline ? 'text-status-success' : 'text-status-error',
                ].join(' ')}
              />
            </motion.div>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.1 }}
                className="ml-2 text-xs text-text-secondary truncate"
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
