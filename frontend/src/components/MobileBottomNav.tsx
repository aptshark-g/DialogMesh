import { NavLink, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  MessageSquare,
  Network,
  UserCircle,
  CheckSquare,
  Settings,
} from 'lucide-react';
import type { ComponentType } from 'react';

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

export function MobileBottomNav() {
  const location = useLocation();

  const isActive = (to: string) => {
    if (location.pathname === to) return true;
    if (to !== '/' && location.pathname.startsWith(to)) return true;
    return false;
  };

  return (
    <nav
      className="lg:hidden fixed bottom-0 inset-x-0 z-50 bg-surface-sidebar border-t border-subtle"
      style={{ paddingBottom: 'env(safe-area-inset-bottom, 0px)' }}
      aria-label="移动端底部导航"
    >
      <div className="flex items-center justify-around h-16">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={`relative flex flex-col items-center justify-center gap-0.5 w-full h-full transition-colors ${
                active ? 'text-primary' : 'text-text-muted hover:text-text-secondary'
              }`}
              aria-current={active ? 'page' : undefined}
            >
              <motion.div
                className="flex flex-col items-center justify-center gap-0.5"
                whileTap={{ scale: 0.88 }}
                transition={{ duration: 0.1 }}
              >
                <Icon
                  className={`w-5 h-5 transition-colors ${
                    active ? 'text-primary' : 'text-text-muted'
                  }`}
                />
                <span
                  className={`text-[10px] font-medium transition-colors ${
                    active ? 'text-primary' : 'text-text-muted'
                  }`}
                >
                  {item.label}
                </span>
              </motion.div>

              {active && (
                <motion.div
                  layoutId="mobile-bottom-nav-indicator"
                  className="absolute top-0 w-8 h-0.5 bg-primary rounded-full"
                  transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                />
              )}
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
