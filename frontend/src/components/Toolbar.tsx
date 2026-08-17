import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Sparkles,
  Settings,
  MoreHorizontal,
  Sun,
  Moon,
} from 'lucide-react';
import { useTheme, useToggleTheme } from '@/stores/themeStore';
import { useOmnibox } from '@/stores/omniboxStore';
import { getProfile } from '@/api/v6';
import { cn } from '@/lib/utils';
import { SessionSwitcher } from './SessionSwitcher';

export interface ToolbarProps {
  sessionTitle: string;
  onSearch?: (query: string) => void;
}

/** 画像状态点(P1-C, B4 临时方案): 复用 /v6/profile 轻量轮询,
 *  绿 = 活跃(n 维), 灰 = 冷启动/加载, 红 = 离线; 点击进画像页。
 *  后端给聚合健康度后(B4)换成单值驱动。 */
function ProfileStatusDot() {
  const navigate = useNavigate();
  const [state, setState] = useState<'loading' | 'active' | 'cold' | 'offline'>('loading');
  const [dims, setDims] = useState(0);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      getProfile()
        .then((p) => {
          if (!alive) return;
          const n = Object.keys(p?.oceAN_dims ?? {}).length;
          setDims(n);
          setState(n > 0 ? 'active' : 'cold');
        })
        .catch(() => { if (alive) setState('offline'); });
    poll();
    const t = setInterval(poll, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const label =
    state === 'active' ? `画像 · ${dims} 维` :
    state === 'cold' ? '画像冷启动' :
    state === 'offline' ? '画像离线' : '画像…';

  return (
    <button
      type="button"
      onClick={() => navigate('/profile')}
      title={`认知画像状态: ${label}(点击打开画像页)`}
      aria-label={`认知画像状态: ${label}`}
      className="flex items-center gap-1.5 h-[30px] px-2 rounded-full hover:bg-surface-card-hover transition-colors"
    >
      <span
        className={cn(
          'w-1.5 h-1.5 rounded-full shrink-0',
          state === 'active' && 'bg-status-success',
          state === 'cold' && 'bg-text-muted',
          state === 'offline' && 'bg-status-error',
          state === 'loading' && 'bg-text-muted animate-pulse'
        )}
      />
      <span className="hidden xl:inline text-[11px] text-text-muted">{label}</span>
    </button>
  );
}

export function Toolbar({ sessionTitle }: ToolbarProps) {
  const isDark = useTheme() === 'dark';
  const toggleTheme = useToggleTheme();
  const openOmnibox = useOmnibox((s) => s.setOpen);

  return (
    <header className="h-[52px] flex items-center justify-between pl-14 pr-4 lg:px-[18px] shrink-0 bg-glass backdrop-blur-xl backdrop-saturate-150 border-b border-hairline shadow-bar-b">
      {/* Left: 会话切换器(P3, 按项目分组) */}
      <SessionSwitcher fallbackTitle={sessionTitle} />

      {/* Center: 万能搜索栏触发器(原装饰性搜索框, 从未接线) — 点击 / Ctrl K 开面板 */}
      <div className="flex-1 max-w-[140px] sm:max-w-md mx-2 sm:mx-4">
        <button
          type="button"
          onClick={() => openOmnibox(true)}
          aria-label="打开万能搜索"
          className="w-full flex items-center gap-2 px-3 py-[5px] rounded-full bg-wash border border-hairline hover:border-primary/40 transition-colors group"
        >
          <Sparkles className="w-3.5 h-3.5 text-primary shrink-0" />
          <span className="flex-1 text-left text-xs text-text-muted truncate group-hover:text-text-secondary transition-colors">
            搜索
          </span>
          <kbd className="hidden sm:inline text-[10px] text-text-muted border border-hairline rounded px-1.5 py-0.5 shrink-0">
            Ctrl K
          </kbd>
        </button>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-1">
        <ProfileStatusDot />

        {/* Theme Toggle */}
        <motion.button
          type="button"
          onClick={toggleTheme}
          className="w-[30px] h-[30px] flex items-center justify-center rounded-full hover:bg-surface-card-hover text-text-secondary transition-colors"
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
                <Sun className="w-[15px] h-[15px]" />
              ) : (
                <Moon className="w-[15px] h-[15px]" />
              )}
            </motion.div>
          </AnimatePresence>
        </motion.button>

        {/* Settings */}
        <button
          type="button"
          className="w-[30px] h-[30px] flex items-center justify-center rounded-full hover:bg-surface-card-hover text-text-secondary transition-colors"
          aria-label="设置"
          title="设置"
        >
          <Settings className="w-[15px] h-[15px]" />
        </button>

        {/* More */}
        <button
          type="button"
          className="w-[30px] h-[30px] flex items-center justify-center rounded-full hover:bg-surface-card-hover text-text-secondary transition-colors"
          aria-label="更多"
          title="更多"
        >
          <MoreHorizontal className="w-[15px] h-[15px]" />
        </button>
      </div>
    </header>
  );
}
