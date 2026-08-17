// FILE: src/pages/PipelinePage.tsx
// Pipeline / Parameters / Context 组装 控制面板
// v10: 新增「调度与降级」卡组 (degradation / sync / causal-chain / TTL / subgraph cache)

import { useState, useCallback, useEffect } from 'react';
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
  Gauge,
  CheckCheck,
  Link2,
  Thermometer,
  Database,
  Loader2,
  Play,
} from 'lucide-react';
import { useV6Pipeline } from '../hooks/useV6Pipeline';
import {
  getSync,
  getCausalChain,
  getDegradation,
  getTtl,
  tickTtl,
  getSubgraphCache,
} from '../api/v6';
import type {
  V6SyncResponse,
  V6CausalChainResponse,
  V6DegradationResponse,
  V6TtlResponse,
  V6TtlTickResponse,
  V6SubgraphCacheResponse,
} from '../types/api';
import { cn } from '../lib/utils';
import { AboutPopover } from '../components/ui/AboutPopover';

// 降级级别分级配色与说明
const DEGRADATION_META: Record<string, { desc: string; cls: string }> = {
  NORMAL: { desc: '全部链路活跃', cls: 'bg-status-success/10 text-status-success' },
  WARNING: { desc: '暂停 Deep Path (因果晋升 / 深度扫描)', cls: 'bg-status-warning/10 text-status-warning' },
  DEGRADED: { desc: '暂停 Meta 审核 / 行为发现 / L5', cls: 'bg-status-processing/10 text-status-processing' },
  EMERGENCY: { desc: '仅核心对话 + 用户编辑', cls: 'bg-status-error/10 text-status-error' },
};

// HCWA 温度配色 (热 → 归档)
const TTL_STATE_CLS: Record<string, string> = {
  active: 'bg-status-error/10 text-status-error',
  paused: 'bg-status-warning/10 text-status-warning',
  cold: 'bg-status-info/10 text-status-info',
  frozen: 'bg-teal/10 text-teal',
  archived: 'bg-status-pending/10 text-status-pending',
};

export function PipelinePage() {
  const {
    pipeline, extraction, perspectives, parameters, context,
    loading, error, saveLoading, saveError,
    refresh, editParams,
  } = useV6Pipeline(true, 10000);

  const [paramValues, setParamValues] = useState<Record<string, number | string | boolean>>({});
  const [editingParams, setEditingParams] = useState<Set<string>>(new Set());
  // 2026-08-18: 参数变更记录（本地会话内, 让调参可追踪）
  const [paramChanges, setParamChanges] = useState<{
    name: string; from: string; to: string; ts: number;
  }[]>([]);
  // 运行模式: 自适应 / 固定（自适应步长本地偏好）
  const [runMode, setRunMode] = useState<'adaptive' | 'fixed'>('adaptive');
  const [adaptiveStep, setAdaptiveStep] = useState(5);

  // ─── 调度与降级 (v10) ───
  const [degradation, setDegradation] = useState<V6DegradationResponse | null>(null);
  const [ttlStats, setTtlStats] = useState<V6TtlResponse | null>(null);
  const [subgraphCache, setSubgraphCache] = useState<V6SubgraphCacheResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [syncBlockId, setSyncBlockId] = useState('');
  const [syncResult, setSyncResult] = useState<V6SyncResponse | null>(null);
  const [syncLoading, setSyncLoading] = useState(false);
  const [chainEvent, setChainEvent] = useState('');
  const [chainResult, setChainResult] = useState<V6CausalChainResponse | null>(null);
  const [chainLoading, setChainLoading] = useState(false);
  const [tickResult, setTickResult] = useState<V6TtlTickResponse | null>(null);
  const [tickLoading, setTickLoading] = useState(false);

  // 静默轮询 (不切换 loading 标志),与页面 10s 节奏一致
  const fetchScheduling = useCallback(async () => {
    const [d, t, c] = await Promise.all([
      getDegradation().catch(() => null),
      getTtl().catch(() => null),
      getSubgraphCache().catch(() => null),
    ]);
    setDegradation(d);
    setTtlStats(t);
    setSubgraphCache(c);
  }, []);

  useEffect(() => {
    fetchScheduling();
    const timer = setInterval(fetchScheduling, 10000);
    return () => clearInterval(timer);
  }, [fetchScheduling]);

  const handleRefresh = useCallback(() => {
    refresh();
    fetchScheduling();
  }, [refresh, fetchScheduling]);

  const handleSync = useCallback(async () => {
    setSyncLoading(true);
    setActionError(null);
    try {
      const id = syncBlockId.trim();
      setSyncResult(await getSync(id || undefined));
    } catch (err) {
      setSyncResult(null);
      setActionError(`强一致读失败: ${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setSyncLoading(false);
    }
  }, [syncBlockId]);

  const handleChainTrace = useCallback(async () => {
    setChainLoading(true);
    setActionError(null);
    try {
      const ev = chainEvent.trim();
      setChainResult(await getCausalChain(ev || undefined));
    } catch (err) {
      setChainResult(null);
      setActionError(`因果链追踪失败: ${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setChainLoading(false);
    }
  }, [chainEvent]);

  const handleTick = useCallback(async () => {
    setTickLoading(true);
    setActionError(null);
    try {
      const resp = await tickTtl();
      setTickResult(resp);
      await fetchScheduling(); // tick 后刷新统计
    } catch (err) {
      setTickResult(null);
      setActionError(`温度迁移失败: ${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setTickLoading(false);
    }
  }, [fetchScheduling]);

  const handleParamChange = useCallback((name: string, value: number | string | boolean) => {
    setParamValues(prev => ({ ...prev, [name]: value }));
    setEditingParams(prev => new Set(prev).add(name));
    // 记录变更（旧值取自初始参数, 失败则记 '?'）
    setParamChanges(prev => {
      const base = parameters?.parameters ?? [];
      const found = base.find((p) => p.name === name);
      const from = found ? String(found.value) : '?';
      const next = [...prev, { name, from, to: String(value), ts: Date.now() }];
      return next.slice(-30);
    });
  }, [parameters]);

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

  const degradationMeta = degradation ? DEGRADATION_META[degradation.level] : undefined;
  const cacheSize = subgraphCache?.size ?? 0;
  const cacheStale = subgraphCache?.stale ?? 0;
  const cacheValidRate = cacheSize > 0 ? (cacheSize - cacheStale) / cacheSize : 0;

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
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
              刷新
            </button>
            <AboutPopover>
              <div className="font-semibold text-text-primary mb-1">这个页面是做什么的</div>
              DialogMesh 把一次对话按<b>认知流水线</b>加工:
              <span className="font-mono text-primary">Event → Observation → Hypothesis → Knowledge → Skill</span>
              （事实 → 候选解释 → 竞争中的信念 → 稳定认知 → 可复用能力）。
              本页控制这条流水线的<b>运行参数</b>（各阶段可调参数、降级级别、强一致读、
              温度迁移、子图缓存）与<b>上下文组装</b>。改参数后立即生效, 调整了什么可在
              「参数变更记录」里看到。
            </AboutPopover>
          </div>
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

        {/* 运行模式（自适应/固定） */}
        <motion.section {...fadeIn(0.04)} className="card-liquid shadow-card rounded-xl p-5">
          <div className="flex items-center gap-2 text-text-muted mb-3">
            <Gauge className="h-4 w-4" />
            <span className="text-xs font-semibold">运行模式</span>
          </div>
          <div className="flex items-center gap-2">
            {(['adaptive', 'fixed'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setRunMode(m)}
                className={cn(
                  'px-3 py-1.5 rounded-full text-xs font-medium border transition-colors',
                  runMode === m
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-gray-200 text-text-secondary hover:text-primary'
                )}
              >
                {m === 'adaptive' ? '自适应' : '固定'}
              </button>
            ))}
          </div>
          {runMode === 'adaptive' && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-xs text-text-muted mb-1.5">
                <span>自适应步长（复杂度分档粒度）</span>
                <span className="font-mono text-text-primary">{adaptiveStep}</span>
              </div>
              <input
                type="range"
                min={1}
                max={10}
                step={1}
                value={adaptiveStep}
                onChange={(e) => setAdaptiveStep(Number(e.target.value))}
                className="w-full h-1.5 rounded-lg appearance-none bg-gray-200 accent-primary cursor-pointer"
              />
              <p className="text-[11px] text-text-muted mt-1.5">
                自适应 = 按查询复杂度自动选择 rule / small_model / remote_llm;
                步长越小分档越细（当前为本地偏好, 与网关路由模式联动开发中）。
              </p>
            </div>
          )}
        </motion.section>

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

          {/* 2026-08-18: 参数变更记录 */}
          {paramChanges.length > 0 && (
            <div className="mt-4 rounded-lg border border-gray-100 p-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-text-primary mb-2">
                <CheckCheck className="w-3.5 h-3.5 text-text-muted" />
                参数变更记录
                <span className="font-normal text-text-muted">（本次会话内）</span>
              </div>
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {[...paramChanges].reverse().map((c, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className="text-text-muted shrink-0">
                      {new Date(c.ts).toLocaleTimeString('zh-CN', { hour12: false })}
                    </span>
                    <span className="font-mono text-text-primary shrink-0">{c.name}</span>
                    <span className="text-text-muted truncate">
                      {c.from} → <span className="text-primary">{c.to}</span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
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

        {/* ─── 调度与降级 (v10 NEW) ─── */}
        <motion.section {...fadeIn(0.25)} className="space-y-4">
          <div className="flex items-center gap-2">
            <Gauge className="h-4 w-4 text-text-muted" />
            <span className="text-xs font-semibold text-text-muted">调度与降级</span>
            <div className="flex-1 border-t border-gray-200" />
            <button
              onClick={fetchScheduling}
              className="flex items-center gap-1 rounded-lg bg-surface-card border border-gray-200 px-2.5 py-1 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors"
            >
              <RefreshCw className="h-3 w-3" />
              刷新
            </button>
          </div>
          {actionError && (
            <div className="rounded-xl bg-status-error/5 text-status-error text-sm px-4 py-3">
              {actionError}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* 降级级别 */}
            <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <Gauge className="h-4 w-4" />
                <span className="text-xs font-semibold">系统降级级别 (/v6/degradation)</span>
              </div>
              {degradation ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <span className={cn(
                      'text-sm font-semibold px-3 py-1 rounded-lg',
                      degradationMeta?.cls ?? 'bg-status-pending/10 text-status-pending'
                    )}>
                      {degradation.level}
                    </span>
                    <span className="text-xs text-text-muted">
                      队列深度 <span className="font-mono text-text-primary">{degradation.queue_depth}</span>
                    </span>
                  </div>
                  <p className="text-xs text-text-secondary">{degradationMeta?.desc ?? '未知级别'}</p>
                </div>
              ) : (
                <div className="text-sm text-text-secondary py-2">暂无数据</div>
              )}
            </div>

            {/* 强一致读 */}
            <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <CheckCheck className="h-4 w-4" />
                <span className="text-xs font-semibold">强一致读 (/v6/sync)</span>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={syncBlockId}
                  onChange={(e) => setSyncBlockId(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleSync(); }}
                  placeholder="block_id (留空则全局 sync)"
                  className="flex-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                />
                <button
                  onClick={handleSync}
                  disabled={syncLoading}
                  className="flex items-center gap-1 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50 shrink-0"
                >
                  {syncLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCheck className="h-3.5 w-3.5" />}
                  {syncLoading ? '同步中...' : '强一致读'}
                </button>
              </div>
              {syncResult && (
                <div className="mt-3 rounded-lg bg-surface-sidebar px-3 py-2 space-y-1">
                  {syncResult.status && (
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-text-muted">状态</span>
                      <span className="font-medium text-status-success">{syncResult.status}</span>
                      <span className="text-text-muted ml-auto">待处理 {syncResult.pending ?? 0}</span>
                    </div>
                  )}
                  {syncResult.block_id && (
                    <>
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-text-muted">block</span>
                        <span className="font-mono text-text-primary">{syncResult.block_id}</span>
                      </div>
                      {syncResult.text && (
                        <p className="text-xs text-text-secondary break-all">{syncResult.text}</p>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>

            {/* 因果链追踪 */}
            <div className="bg-surface-card rounded-xl border border-gray-200 p-5 md:col-span-2">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <Link2 className="h-4 w-4" />
                <span className="text-xs font-semibold">因果链追踪 (/v6/causal-chain) — 前端乐观更新</span>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={chainEvent}
                  onChange={(e) => setChainEvent(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleChainTrace(); }}
                  placeholder="event 名称 (留空查看全局统计)"
                  className="flex-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                />
                <button
                  onClick={handleChainTrace}
                  disabled={chainLoading}
                  className="flex items-center gap-1 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50 shrink-0"
                >
                  {chainLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Link2 className="h-3.5 w-3.5" />}
                  {chainLoading ? '追踪中...' : '追踪'}
                </button>
              </div>

              {/* 链时间线 */}
              {chainResult?.chain && (
                <div className="mt-4">
                  {chainResult.chain.length === 0 ? (
                    <div className="text-sm text-text-secondary py-2">该事件暂无因果链</div>
                  ) : (
                    <div>
                      {chainResult.chain.map((node, idx) => (
                        <div key={`${node.event}-${idx}`} className="flex items-stretch gap-3">
                          <div className="flex flex-col items-center">
                            <div className={cn(
                              'h-2.5 w-2.5 rounded-full mt-1.5 shrink-0',
                              idx === 0 ? 'bg-primary' : 'bg-primary/50'
                            )} />
                            {idx < chainResult.chain!.length - 1 && (
                              <div className="w-px flex-1 bg-primary/20" />
                            )}
                          </div>
                          <div className="pb-4">
                            <div className="text-sm font-mono text-text-primary">{node.event}</div>
                            <div className="text-xs text-text-muted">depth {node.depth}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {chainResult.remaining !== undefined && (
                    <div className="text-xs text-text-muted mt-1 pl-6">
                      预计剩余链长 (P90): <span className="font-mono text-text-primary">{chainResult.remaining}</span>
                    </div>
                  )}
                </div>
              )}

              {/* 全局统计 (未指定 event) */}
              {chainResult && !chainResult.chain && (
                <div className="mt-3 grid grid-cols-3 gap-2">
                  <div className="bg-surface-sidebar rounded-lg p-3">
                    <span className="text-xs text-text-muted">追踪中链</span>
                    <p className="text-lg font-semibold text-text-primary">{chainResult.tracked_chains ?? 0}</p>
                  </div>
                  <div className="bg-surface-sidebar rounded-lg p-3">
                    <span className="text-xs text-text-muted">平均链长</span>
                    <p className="text-lg font-semibold text-text-primary">{(chainResult.avg_chain_length ?? 0).toFixed(1)}</p>
                  </div>
                  <div className="bg-surface-sidebar rounded-lg p-3">
                    <span className="text-xs text-text-muted">P90 链长</span>
                    <p className="text-lg font-semibold text-text-primary">{chainResult.p90_chain_length ?? 0}</p>
                  </div>
                </div>
              )}
            </div>

            {/* TTL 温度迁移 */}
            <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2 text-text-muted">
                  <Thermometer className="h-4 w-4" />
                  <span className="text-xs font-semibold">HCWA 温度迁移 (/v6/ttl)</span>
                </div>
                <button
                  onClick={handleTick}
                  disabled={tickLoading}
                  className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-2.5 py-1 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
                >
                  {tickLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                  {tickLoading ? '迁移中...' : '手动 tick'}
                </button>
              </div>
              {ttlStats?.error ? (
                <div className="text-sm text-text-secondary py-2">引擎未就绪: {ttlStats.error}</div>
              ) : ttlStats ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(ttlStats.by_state ?? {}).map(([state, count]) => (
                      <span
                        key={state}
                        className={cn(
                          'text-xs font-medium px-2 py-1 rounded',
                          TTL_STATE_CLS[state] ?? 'bg-status-pending/10 text-status-pending'
                        )}
                      >
                        {state} · {count}
                      </span>
                    ))}
                    {Object.keys(ttlStats.by_state ?? {}).length === 0 && (
                      <span className="text-xs text-text-muted">暂无节点</span>
                    )}
                  </div>
                  <div className="text-xs text-text-muted">
                    总节点 <span className="font-mono text-text-primary">{ttlStats.total ?? 0}</span>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-text-secondary py-2">暂无数据</div>
              )}
              {tickResult && !tickResult.error && (
                <div className="mt-3 rounded-lg bg-surface-sidebar px-3 py-2 space-y-1">
                  <div className="text-xs">
                    <span className="text-text-muted">升温 promoted: </span>
                    <span className="font-mono text-status-success">{(tickResult.promoted ?? []).length}</span>
                    <span className="text-text-muted ml-3">降温 demoted: </span>
                    <span className="font-mono text-status-warning">{(tickResult.demoted ?? []).length}</span>
                  </div>
                  {[...(tickResult.promoted ?? []), ...(tickResult.demoted ?? [])].slice(0, 5).map((c) => (
                    <div key={c} className="text-xs font-mono text-text-secondary">{c}</div>
                  ))}
                </div>
              )}
              {tickResult?.error && (
                <div className="mt-3 text-xs text-status-error">引擎未就绪: {tickResult.error}</div>
              )}
            </div>

            {/* 子图缓存 */}
            <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <Database className="h-4 w-4" />
                <span className="text-xs font-semibold">子图缓存 (/v6/subgraph/cache)</span>
              </div>
              {subgraphCache?.error ? (
                <div className="text-sm text-text-secondary py-2">引擎未就绪: {subgraphCache.error}</div>
              ) : subgraphCache ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-3 gap-2">
                    <div className="bg-surface-sidebar rounded-lg p-3">
                      <span className="text-xs text-text-muted">缓存条目</span>
                      <p className="text-lg font-semibold text-text-primary">{cacheSize}</p>
                    </div>
                    <div className="bg-surface-sidebar rounded-lg p-3">
                      <span className="text-xs text-text-muted">累计命中</span>
                      <p className="text-lg font-semibold text-status-success">{subgraphCache.hits ?? 0}</p>
                    </div>
                    <div className="bg-surface-sidebar rounded-lg p-3">
                      <span className="text-xs text-text-muted">过期条目</span>
                      <p className="text-lg font-semibold text-status-warning">{cacheStale}</p>
                    </div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between text-xs text-text-muted mb-1">
                      <span>有效缓存占比</span>
                      <span className="font-mono text-text-primary">{Math.round(cacheValidRate * 100)}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-surface-sidebar overflow-hidden">
                      <div
                        className="h-2 rounded-full bg-primary transition-all duration-500"
                        style={{ width: `${cacheValidRate * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-text-secondary py-2">暂无数据</div>
              )}
            </div>
          </div>
        </motion.section>
      </div>
    </div>
  );
}
