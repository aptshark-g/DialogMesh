import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sun, Moon } from 'lucide-react';
import { useTheme, useThemeStore } from '@/stores/themeStore';
import { cn } from '@/lib/utils';

interface ThemeToggleProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  className?: string;
}

const ThemeToggle: React.FC<ThemeToggleProps> = ({ className, ...props }) => {
  const theme = useTheme();
  const isDark = theme === 'dark';

  return (
    <button
      type="button"
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className={cn(
        'inline-flex items-center justify-center',
        'w-9 h-9 rounded-full',
        'bg-surface-card border border-subtle',
        'text-[#A9A5B8] hover:text-[#E8E6F0]',
        'hover:border-medium transition-colors duration-200',
        'focus:outline-none focus:ring-2 focus:ring-[#D97706]/50',
        className
      )}
      {...props}
      onClick={(e) => {
        useThemeStore.getState().toggleTheme();
        props.onClick?.(e);
      }}
    >
      <AnimatePresence mode="wait" initial={false}>
        {isDark ? (
          <motion.div
            key="moon"
            initial={{ rotate: -90, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            exit={{ rotate: 90, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <Moon className="h-4 w-4" />
          </motion.div>
        ) : (
          <motion.div
            key="sun"
            initial={{ rotate: 90, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            exit={{ rotate: -90, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <Sun className="h-4 w-4" />
          </motion.div>
        )}
      </AnimatePresence>
    </button>
  );
};

export { ThemeToggle };
export type { ThemeToggleProps };
