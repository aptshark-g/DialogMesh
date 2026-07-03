import { useState, useEffect, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  ChevronDown,
  Search,
  Settings,
  MoreHorizontal,
  Sun,
  Moon,
} from 'lucide-react';

export interface ToolbarProps {
  sessionTitle: string;
  onSearch?: (query: string) => void;
}

function useThemeToggle() {
  const [isDark, setIsDark] = useState(() => {
    if (typeof window === 'undefined') return true;
    const stored = localStorage.getItem('dialogmesh-theme');
    if (stored) return stored === 'dark';
    return true;
  });

  useEffect(() => {
    const root = document.documentElement;
    if (isDark) {
      root.classList.remove('light');
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
      root.classList.add('light');
    }
    localStorage.setItem('dialogmesh-theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  const toggle = useCallback(() => setIsDark((prev) => !prev), []);

  return { isDark, toggle };
}

export function Toolbar({ sessionTitle, onSearch }: ToolbarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const { isDark, toggle } = useThemeToggle();

  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setSearchQuery(e.target.value);
      onSearch?.(e.target.value);
    },
    [onSearch]
  );

  return (
    <header className="h-12 flex items-center justify-between pl-14 pr-4 lg:px-4 border-b border-subtle bg-surface shrink-0">
      {/* Left: Session Title */}
      <div className="flex items-center gap-2 min-w-0">
        <button
          type="button"
          className="flex items-center gap-1.5 text-base sm:text-lg font-semibold text-text-primary hover:text-primary transition-colors"
        >
          <span className="truncate">{sessionTitle}</span>
          <ChevronDown className="w-4 h-4 text-text-muted shrink-0" />
        </button>
      </div>

      {/* Center: Search */}
      <div className="flex-1 max-w-[140px] sm:max-w-md mx-2 sm:mx-4">
        <div
          className={[
            'flex items-center gap-2 px-2 sm:px-3 py-1.5 rounded-md bg-surface-card border transition-colors',
            searchFocused ? 'border-primary' : 'border-subtle',
          ].join(' ')}
        >
          <Search className="w-4 h-4 text-text-muted shrink-0" />
          <input
            type="text"
            value={searchQuery}
            onChange={handleSearchChange}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            placeholder="搜索"
            className="w-full bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
          />
        </div>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-1">
        {/* Theme Toggle */}
        <motion.button
          type="button"
          onClick={toggle}
          className="w-9 h-9 flex items-center justify-center rounded-full bg-surface-card border border-subtle hover:bg-surface-card-hover text-text-secondary transition-colors"
          aria-label={isDark ? '切换到亮色模式' : '切换到暗色模式'}
          title={isDark ? '切换到亮色模式' : '切换到暗色模式'}
          whileTap={{ scale: 0.95 }}
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={isDark ? 'dark' : 'light'}
              initial={{ rotate: -90, opacity: 0 }}
              animate={{ rotate: 0, opacity: 1 }}
              exit={{ rotate: 90, opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              {isDark ? (
                <Sun className="w-4 h-4" />
              ) : (
                <Moon className="w-4 h-4" />
              )}
            </motion.div>
          </AnimatePresence>
        </motion.button>

        {/* Settings */}
        <button
          type="button"
          className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-surface-card-hover text-text-secondary transition-colors"
          aria-label="设置"
          title="设置"
        >
          <Settings className="w-4 h-4" />
        </button>

        {/* More */}
        <button
          type="button"
          className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-surface-card-hover text-text-secondary transition-colors"
          aria-label="更多"
          title="更多"
        >
          <MoreHorizontal className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
