// FILE: src/pages/DeepChainPage.tsx
// Deep Chain: Relations + Causal + Behavior + Engineering 深层链面板

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Link2,
  GitBranch,
  BrainCircuit,
  Wrench,
  RefreshCw,
  ChevronRight,
  ChevronDown,
  Network,
  Activity,
} from 'lucide-react';
import { useV6DeepChain } from '../hooks/useV6DeepChain';
import { cn } from '../lib/utils';

type TabKey = 'relations' | 'causal' | 'behavior' | 'engineering';

const tabs: { key: TabKey; label: string; icon: typeof Link2 }[] = [
  { key: 'relations', label: '关系底物', icon: Link2 },
  { key: 'causal', label: '因果链', icon: GitBranch },
  { key: 'behavior', label: '行为图', icon: BrainCircuit },
  { key: 'engineering', label: '工程约束', icon: Wrench },
];

export function DeepChainPage() {
  const { relations, causal, behavior, engineering, loading, error, refresh } = useV6DeepChain();
  const [activeTab, setActiveTab] = useState<TabKey>('relations');
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());

  const toggleExpand = (key: string) => {
    setExpandedKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const fadeIn = (delay: number) => ({
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, delay },
  });

  // Render any JSON-like data as a tree
  const renderTree = (data: Record<string, unknown> | unknown[] | null, prefix = '') => {
    if (data === null || data === undefined) return <p className="text-sm text-text-muted">暂无数据</p>;
    if (Array.isArray(data)) {
      if (data.length === 0) return <p className="text-sm text-text-muted">空列表</p>;
      return (
        <div className="space-y-1">
          {data.map((item, idx) => (
            <div key={`${prefix}-${idx}`} className="rounded-lg border border-gray-100 p-2">
              {typeof item === 'object' && item !== null ? renderTree(item as Record<string, unknown>, `${prefix}-${idx}`) : (
                <span className="text-sm text-text-primary">{String(item)}</span>
              )}
            </div>
          ))}
        </div>
      );
    }
    if (typeof data === 'object') {
      const entries = Object.entries(data);
      if (entries.length === 0) return <p className="text-sm text-text-muted">空对象</p>;
      return (
        <div className="space-y-1">
          {entries.map(([k, v]) => {
            const keyPath = `${prefix}.${k}`;
            const isExpanded = expandedKeys.has(keyPath);
            const isNested = typeof v === 'object' && v !== null;
            return (
              <div key={keyPath} className="rounded-lg border border-gray-50 hover:border-gray-200 transition-colors">
                <button
                  onClick={() => isNested && toggleExpand(keyPath)}
                  className={cn(
                    'w-full flex items-center gap-2 px-3 py-2 text-left',
                    isNested ? 'cursor-pointer' : 'cursor-default'
                  )}
                >
                  {isNested ? (
                    isExpanded ? <ChevronDown className="h-3.5 w-3.5 text-text-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-text-muted" />
                  ) : (
                    <span className="w-3.5" />
                  )}
                  <span className="text-xs font-medium text-text-muted shrink-0">{k}</span>
                  {!isNested && (
                    <span className="text-sm text-text-primary font-mono break-all">{String(v)}</span>
                  )}
                </button>
                <AnimatePresence>
                  {isNested && isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="px-3 pb-2 pl-8">
                        {renderTree(v as Record<string, unknown> | unknown[], keyPath)}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      );
    }
    return <span className="text-sm text-text-primary">{String(data)}</span>;
  };

  const getData = () => {
    switch (activeTab) {
      case 'relations': return relations;
      case 'causal': return causal;
      case 'behavior': return behavior;
      case 'engineering': return engineering;
      default: return null;
    }
  };

  const data = getData();
  const isEmpty = !data || Object.keys(data).length === 0;

  return (
    <div className="min-h-screen bg-surface-main">
      {/* Header */}
      <header className="bg-surface-card border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-primary flex items-center justify-center">
              <Network className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-text-primary">深层链</h1>
              <p className="text-xs text-text-muted">关系底物 · 因果链 · 行为图 · 工程约束</p>
            </div>
          </div>
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            刷新
          </button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {error && (
          <div className="rounded-xl bg-status-error/5 text-status-error text-sm px-4 py-3">
            {error}
          </div>
        )}

        {/* Tabs */}
        <motion.div {...fadeIn(0.05)} className="flex gap-1 overflow-x-auto pb-1">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap',
                  isActive
                    ? 'bg-primary text-white'
                    : 'bg-surface-card text-text-secondary hover:text-text-primary border border-gray-200'
                )}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </motion.div>

        {/* Data Panel */}
        <motion.section
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="bg-surface-card rounded-xl border border-gray-200 p-5"
        >
          <div className="flex items-center gap-2 text-text-muted mb-4">
            {(() => {
              const Icon = tabs.find(t => t.key === activeTab)?.icon || Activity;
              return <Icon className="h-4 w-4" />;
            })()}
            <span className="text-xs font-semibold">{tabs.find(t => t.key === activeTab)?.label} 数据</span>
          </div>

          {isEmpty ? (
            <div className="text-center py-16">
              <Network className="h-10 w-10 text-text-muted mx-auto mb-3" />
              <p className="text-sm text-text-secondary">暂无数据</p>
              <p className="text-xs text-text-muted mt-1">后端可能尚未实现此端点</p>
            </div>
          ) : (
            renderTree(data)
          )}
        </motion.section>

        {/* Stats summary */}
        {data && !isEmpty && (
          <motion.div {...fadeIn(0.15)} className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="bg-surface-card rounded-lg border border-gray-200 p-3">
              <span className="text-xs text-text-muted">顶层键</span>
              <p className="text-lg font-semibold text-text-primary">{Object.keys(data).length}</p>
            </div>
            <div className="bg-surface-card rounded-lg border border-gray-200 p-3">
              <span className="text-xs text-text-muted">嵌套层数</span>
              <p className="text-lg font-semibold text-text-primary">{getDepth(data)}</p>
            </div>
            <div className="bg-surface-card rounded-lg border border-gray-200 p-3">
              <span className="text-xs text-text-muted">总节点数</span>
              <p className="text-lg font-semibold text-text-primary">{getNodeCount(data)}</p>
            </div>
            <div className="bg-surface-card rounded-lg border border-gray-200 p-3">
              <span className="text-xs text-text-muted">数组项</span>
              <p className="text-lg font-semibold text-text-primary">{getArrayCount(data)}</p>
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

function getDepth(data: unknown): number {
  if (data === null || typeof data !== 'object') return 0;
  if (Array.isArray(data)) {
    return data.length > 0 ? 1 + Math.max(0, ...data.map(getDepth)) : 1;
  }
  const values = Object.values(data as Record<string, unknown>);
  if (values.length === 0) return 1;
  return 1 + Math.max(0, ...values.map(getDepth));
}

function getNodeCount(data: unknown): number {
  if (data === null || typeof data !== 'object') return 1;
  if (Array.isArray(data)) return data.reduce((sum, v) => sum + getNodeCount(v), 1);
  return Object.values(data as Record<string, unknown>).reduce((sum, v) => sum + getNodeCount(v), 1);
}

function getArrayCount(data: unknown): number {
  if (Array.isArray(data)) return data.length + data.reduce((sum, v) => sum + getArrayCount(v), 0);
  if (data !== null && typeof data === 'object') {
    return Object.values(data as Record<string, unknown>).reduce((sum, v) => sum + getArrayCount(v), 0);
  }
  return 0;
}
