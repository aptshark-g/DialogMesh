// FILE: src/pages/PipelinePage.tsx
// Pipeline / Parameters / Context 组装 控制面板

import { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  Workflow,
  Settings2,
  Eye,
  FileText,
  RefreshCw,
  Save,
  Layers,
  Target,
  ChevronRight,
} from 'lucide-react';
import { useV6Pipeline } from '../hooks/useV6Pipeline';
import { cn } from '../lib/utils';

export function PipelinePage() {
  const {
    pipeline, extraction, perspectives, parameters, context,
    loading, error, saveLoading, saveError,
    refresh, editParams,
  } = useV6Pipeline(true, 10000);

  const [paramValues, setParamValues] = useState<Record<string, number | string | boolean>>({});
  const [editingParams, setEditingParams] = useState<Set<string>>(new Set());

  const handleParamChange = useCallback((name: string, value: number | string | boolean) => {
    setParamValues(prev => ({ ...prev, [name]: value }));
    setEditingParams(prev => new Set(prev).add(name));
  }, []);

  const handleSaveParams = useCallback(() => {
    if (editingParams.size === 0) return;
    const toSave: Record<string, number | string | boolean> = {};
    editingParams.forEach(name => {
      toSave[name] = paramValues[name];
    });
    editParams({ parameters: toSave });
    setEditingParams(new Set());
  }, [editingParams, paramValues, editParams]);

  const fadeIn = (delay: number) => ({
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, delay },
  });

  // Render pipeline data as key-value pairs
  const renderKv = (data: Record<string, unknown> | null, emptyText = '暂无数据') => {
    if (!data || Object.keys(data).length === 0) return <p className="text-sm text-text-secondary py-2">{emptyText}</p>;
    return (
      <div className="space-y-2">
        {Object.entries(data).map(([k, v]) => (
          <div key={k} className="flex items-start justify-between gap-2">
            <span className="text-xs text-text-muted shrink-0">{k}</span>
            <span className="text-sm text-text-primary font-mono text-right break-all">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-surface-main">
      {/* Header */}
      <header className="bg-surface-card border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-primary flex items-center justify-center">
              <Workflow className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-text-primary">业务管道</h1>
              <p className="text-xs text-text-muted">Pipeline 层级 · 参数调整 · 上下文组装</p>
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
        {saveError && (
          <div className="rounded-xl bg-status-error/5 text-status-error text-sm px-4 py-3">
            {saveError}
          </div>
        )}

        {/* Pipeline Stats */}
        <motion.section {...fadeIn(0.05)} className="bg-surface-card rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-2 text-text-muted mb-4">
            <Layers className="h-4 w-4" />
            <span className="text-xs font-semibold">管道层级</span>
          </div>
          {renderKv(pipeline as Record<string, unknown> | null)}
        </motion.section>

        {/* Parameters */}
        <motion.section {...fadeIn(0.1)} className="bg-surface-card rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-text-muted">
              <Settings2 className="h-4 w-4" />
              <span className="text-xs font-semibold">可调参数</span>
            </div>
            {editingParams.size > 0 && (
              <button
                onClick={handleSaveParams}
                disabled={saveLoading}
                className="flex items-center gap-1.5 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5" />
                {saveLoading ? '保存中...' : `保存 ${editingParams.size} 项`}
              </button>
            )}
          </div>

          {parameters?.parameters && parameters.parameters.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {parameters.parameters.map((param) => {
                const edited = editingParams.has(param.name);
                const currentValue = edited ? paramValues[param.name] : param.value;
                const isBool = typeof param.value === 'boolean';
                const isNum = typeof param.value === 'number';
                return (
                  <div
                    key={param.name}
                    className={cn(
                      'rounded-lg border p-3 transition-colors',
                      edited ? 'border-primary bg-primary/3' : 'border-gray-200'
                    )}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-text-primary">{param.name}</span>
                      {param.editable && (
                        <span className="text-xs text-primary font-medium">可编辑</span>
                      )}
                    </div>
                    {param.description && (
                      <p className="text-xs text-text-muted mb-2">{param.description}</p>
                    )}
                    {isBool ? (
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={Boolean(currentValue)}
                          onChange={(e) => handleParamChange(param.name, e.target.checked)}
                          disabled={!param.editable}
                          className="rounded border-gray-300 text-primary focus:ring-primary"
                        />
                        <span className="text-sm text-text-secondary">{currentValue ? '开启' : '关闭'}</span>
                      </label>
                    ) : isNum && param.range ? (
                      <div className="space-y-2">
                        <input
                          type="range"
                          min={param.range[0]}
                          max={param.range[1]}
                          step={typeof param.range[0] === 'number' && param.range[1] - param.range[0] > 10 ? 1 : 0.01}
                          value={Number(currentValue)}
                          onChange={(e) => handleParamChange(param.name, Number(e.target.value))}
                          disabled={!param.editable}
                          className="w-full h-1.5 rounded-lg appearance-none bg-gray-200 accent-primary cursor-pointer"
                        />
                        <div className="flex items-center justify-between text-xs text-text-muted">
                          <span>{param.range[0]}</span>
                          <span className="font-mono text-text-primary">{Number(currentValue).toFixed(3)}</span>
                          <span>{param.range[1]}</span>
                        </div>
                      </div>
                    ) : (
                      <input
                        type="text"
                        value={String(currentValue ?? '')}
                        onChange={(e) => handleParamChange(param.name, e.target.value)}
                        disabled={!param.editable}
                        className="w-full rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary disabled:opacity-50"
                      />
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-sm text-text-secondary py-4">暂无参数</div>
          )}
          {parameters && (
            <div className="mt-3 text-xs text-text-muted">总计: {parameters.total} 个参数</div>
          )}
        </motion.section>

        {/* Extraction & Perspectives */}
        <motion.section {...fadeIn(0.15)} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 text-text-muted mb-4">
              <Eye className="h-4 w-4" />
              <span className="text-xs font-semibold">提取蓝图</span>
            </div>
            {renderKv(extraction as Record<string, unknown> | null)}
          </div>
          <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 text-text-muted mb-4">
              <Target className="h-4 w-4" />
              <span className="text-xs font-semibold">视角规划器</span>
            </div>
            {renderKv(perspectives as Record<string, unknown> | null)}
          </div>
        </motion.section>

        {/* Context Assembly */}
        <motion.section {...fadeIn(0.2)} className="bg-surface-card rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-2 text-text-muted mb-4">
            <FileText className="h-4 w-4" />
            <span className="text-xs font-semibold">上下文组装</span>
          </div>
          {context ? (
            <div className="space-y-4">
              {context.intent_category && (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-text-secondary">意图分类</span>
                  <span className="text-xs font-medium px-2 py-1 rounded-md bg-primary/10 text-primary">
                    {context.intent_category}
                  </span>
                </div>
              )}
              {context.total_tokens !== undefined && (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-text-secondary">总 Tokens</span>
                  <span className="text-sm font-mono text-text-primary">{context.total_tokens.toLocaleString()}</span>
                </div>
              )}
              {context.entries && context.entries.length > 0 && (
                <div className="mt-3">
                  <div className="text-xs text-text-muted mb-2">条目 ({context.entries.length})</div>
                  <div className="space-y-2">
                    {context.entries.map((entry, idx) => (
                      <div key={idx} className="rounded-lg border border-gray-100 p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-surface-sidebar text-text-primary">{entry.domain}</span>
                          <span className="text-xs text-text-muted">{entry.type}</span>
                          <span className="text-xs text-text-muted ml-auto">置信度 {(entry.confidence * 100).toFixed(1)}%</span>
                        </div>
                        <p className="text-sm text-text-secondary truncate">{entry.content}</p>
                        <div className="flex items-center gap-1 mt-1 text-xs text-text-muted">
                          <ChevronRight className="h-3 w-3" />
                          ~{entry.estimated_tokens} tokens
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-sm text-text-secondary py-4">暂无上下文数据</div>
          )}
        </motion.section>
      </div>
    </div>
  );
}
