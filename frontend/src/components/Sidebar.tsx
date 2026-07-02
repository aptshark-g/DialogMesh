import { useState } from 'react';
import type { ComponentType } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Home,
  Layers,
  Settings,
  Menu,
  X,
  Activity,
  Zap,
  Bot,
} from 'lucide-react';
import { useHealth } from '../hooks/useHealth.ts';

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}

const navItems: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: Home },
  { to: '/sessions', label: 'Session', icon: Layers },
  { to: '/settings', label: '设置', icon: Settings },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  const { health, error } = useHealth();

  const isOnline = health !== null && error === null;

  return (
    <>
      {/* Mobile Toggle */}
      <button
        type="button"
        onClick={() => setMobileOpen((v) => !v)}
        className="fixed top-4 left-4 z-50 p-2 rounded-lg bg-surface-card shadow-md border border-gray-200 lg:hidden"
        aria-label={mobileOpen ? '关闭菜单' : '打开菜单'}
      >
        {mobileOpen ? (
          <X className="w-5 h-5 text-text-primary" />
        ) : (
          <Menu className="w-5 h-5 text-text-primary" />
        )}
      </button>

      {/* Mobile Overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-30 lg:hidden"
          onClick={() => setMobileOpen(false)}
          role="presentation"
        />
      )}

      {/* Sidebar */}
      <aside
        className={[
          'fixed lg:static inset-y-0 left-0 z-40',
          'bg-surface-sidebar border-r border-gray-200',
          'flex flex-col transition-all duration-300',
          collapsed ? 'w-16' : 'w-64',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        ].join(' ')}
      >
        {/* Logo */}
        <div className="h-16 flex items-center px-4 border-b border-gray-200">
          <Bot className="w-7 h-7 text-primary shrink-0" />
          {!collapsed && (
            <span className="ml-3 font-semibold text-text-primary text-lg truncate">
              DialogMesh
            </span>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.to;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMobileOpen(false)}
                className={[
                  'flex items-center px-3 py-2.5 rounded-lg transition-colors',
                  'text-sm font-medium',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-text-secondary hover:bg-gray-100 hover:text-text-primary',
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
                  <span className="ml-3 truncate">{item.label}</span>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Bottom: Health & Collapse */}
        <div className="border-t border-gray-200 p-3 space-y-2">
          {/* Health Status */}
          <div
            className={[
              'flex items-center px-3 py-2 rounded-lg',
              'bg-surface-card border border-gray-200',
            ].join(' ')}
            title={isOnline ? '后端服务正常' : '后端服务异常'}
          >
            <Activity
              className={[
                'w-4 h-4 shrink-0',
                isOnline ? 'text-status-success' : 'text-status-error',
              ].join(' ')}
            />
            {!collapsed && (
              <span className="ml-2 text-xs text-text-secondary truncate">
                {isOnline ? 'Backend Online' : 'Backend Offline'}
              </span>
            )}
          </div>

          {/* Collapse Toggle (desktop only) */}
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            className={[
              'hidden lg:flex items-center px-3 py-2 rounded-lg',
              'text-text-muted hover:text-text-primary hover:bg-gray-100',
              'text-xs transition-colors w-full',
            ].join(' ')}
            aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            <Zap className="w-4 h-4 shrink-0" />
            {!collapsed && (
              <span className="ml-2">{collapsed ? '展开' : '收起'}</span>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
