import { useState, useRef } from 'react';
import { cn } from '@/lib/utils';
import {
  Search,
  ZoomIn,
  ZoomOut,
  Maximize,
  Minimize,
  GitBranch,
  Clock,
  LayoutList,
  Check,
} from 'lucide-react';
import { Tooltip } from '@/components/ui/Tooltip';
import type { ViewMode } from '@/types/graph';
import { INTENT_COLOR_MAP } from '@/types/graph';

export interface GraphToolbarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  activeFilters: string[];
  onFilterToggle: (intent: string) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  zoomLevel: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onResetZoom: () => void;
  onToggleFullscreen?: () => void;
  isFullscreen?: boolean;
  nodeCounts?: Record<string, number>;
}

const VIEW_MODE_OPTIONS: { value: ViewMode; label: string; icon: typeof GitBranch }[] = [
  { value: 'force', label: '力导向', icon: GitBranch },
  { value: 'timeline', label: '时间线', icon: Clock },
  { value: 'tree', label: '树形', icon: LayoutList },
];

export function GraphToolbar({
  searchQuery,
  onSearchChange,
  activeFilters,
  onFilterToggle,
  viewMode,
  onViewModeChange,
  zoomLevel,
  onZoomIn,
  onZoomOut,
  onResetZoom,
  onToggleFullscreen,
  isFullscreen = false,
  nodeCounts = {},
}: GraphToolbarProps) {
  const [searchFocused, setSearchFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const allIntents = Object.entries(INTENT_COLOR_MAP);

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      onSearchChange('');
      inputRef.current?.blur();
    }
  };

  return (
    <div className="flex flex-col gap-3 px-4 py-3 border-b border-subtle bg-surface shrink-0">
      {/* Top row: search + view mode + zoom */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Search */}
        <div className="flex items-center gap-2 flex-1 min-w-0 max-w-md">
          <div
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-md bg-surface-card border transition-colors w-full',
              searchFocused ? 'border-primary' : 'border-subtle'
            )}
          >
            <Search className="w-4 h-4 text-text-muted shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setSearchFocused(false)}
              onKeyDown={handleSearchKeyDown}
              placeholder="搜索节点内容..."
              className="w-full bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => onSearchChange('')}
                className="text-text-muted hover:text-text-secondary shrink-0"
                aria-label="清除搜索"
              >
                <span className="text-xs">×</span>
              </button>
            )}
          </div>
        </div>

        {/* View Mode */}
        <div className="flex items-center bg-surface-card rounded-md border border-subtle p-0.5 shrink-0">
          {VIEW_MODE_OPTIONS.map((option) => {
            const Icon = option.icon;
            const isActive = viewMode === option.value;
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => onViewModeChange(option.value)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-sm transition-colors',
                  isActive
                    ? 'bg-primary text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-card-hover'
                )}
                aria-pressed={isActive}
                title={option.label}
              >
                <Icon className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{option.label}</span>
              </button>
            );
          })}
        </div>

        {/* Zoom controls */}
        <div className="flex items-center gap-1 bg-surface-card rounded-md border border-subtle p-0.5 shrink-0">
          <Tooltip content="缩小" position="top">
            <button
              type="button"
              onClick={onZoomOut}
              className="p-1.5 rounded-sm text-text-secondary hover:text-text-primary hover:bg-surface-card-hover transition-colors"
              aria-label="缩小"
            >
              <ZoomOut className="w-4 h-4" />
            </button>
          </Tooltip>
          <span className="text-xs font-medium text-text-secondary w-12 text-center tabular-nums">
            {Math.round(zoomLevel * 100)}%
          </span>
          <Tooltip content="放大" position="top">
            <button
              type="button"
              onClick={onZoomIn}
              className="p-1.5 rounded-sm text-text-secondary hover:text-text-primary hover:bg-surface-card-hover transition-colors"
              aria-label="放大"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
          </Tooltip>
          <Tooltip content="重置缩放" position="top">
            <button
              type="button"
              onClick={onResetZoom}
              className="p-1.5 rounded-sm text-text-secondary hover:text-text-primary hover:bg-surface-card-hover transition-colors"
              aria-label="重置缩放"
            >
              <span className="text-xs font-medium">1:1</span>
            </button>
          </Tooltip>
        </div>

        {/* Fullscreen toggle */}
        {onToggleFullscreen && (
          <Tooltip content={isFullscreen ? '退出全屏' : '全屏'} position="top">
            <button
              type="button"
              onClick={onToggleFullscreen}
              className="p-2 rounded-md bg-surface-card border border-subtle text-text-secondary hover:text-text-primary hover:bg-surface-card-hover transition-colors shrink-0"
              aria-label={isFullscreen ? '退出全屏' : '全屏'}
            >
              {isFullscreen ? (
                <Minimize className="w-4 h-4" />
              ) : (
                <Maximize className="w-4 h-4" />
              )}
            </button>
          </Tooltip>
        )}
      </div>

      {/* Bottom row: intent filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-text-muted mr-1">意图过滤:</span>
        {allIntents.map(([intentKey, config]) => {
          const isActive = activeFilters.includes(intentKey);
          const count = nodeCounts[intentKey] ?? 0;
          return (
            <button
              key={intentKey}
              type="button"
              onClick={() => onFilterToggle(intentKey)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-all',
                isActive
                  ? 'border-transparent text-white'
                  : 'border-subtle text-text-muted bg-surface-card hover:text-text-secondary'
              )}
              style={
                isActive
                  ? { backgroundColor: config.hex, borderColor: config.hex }
                  : undefined
              }
              aria-pressed={isActive}
              title={config.label}
            >
              {isActive && <Check className="w-3 h-3" />}
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: config.hex }}
              />
              <span>{config.label}</span>
              {count > 0 && (
                <span
                  className={cn(
                    'text-[10px] tabular-nums ml-0.5',
                    isActive ? 'text-white/80' : 'text-text-muted'
                  )}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
