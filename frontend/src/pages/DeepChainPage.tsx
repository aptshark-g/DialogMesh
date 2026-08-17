// FILE: src/pages/DeepChainPage.tsx
// Deep Chain: Relations + Causal + Behavior + Engineering + Belief + Subgraph 深层链面板

import { useState, useCallback } from 'react';
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
  Brain,
  GitFork,
  Lock,
  Search,
} from 'lucide-react';
import { useV6DeepChain } from '../hooks/useV6DeepChain';
import { getBelief, getSubgraph } from '../api/v6';
import type {
  V6RelationsResponse,
  V6CausalResponse,
  V6BehaviorResponse,
  V6EngineeringResponse,
  V6BeliefResponse,
  V6BeliefEntry,
  V6SubgraphResponse,
} from '../types/api';
import { cn } from '../lib/utils';

type TabKey = 'relations' | 'causal' | 'behavior' | 'engineering' | 'belief' | 'subgraph';
type Perspective = 'dialogue' | 'meta';

const tabs: { key: TabKey; label: string; icon: typeof Link2 }[] = [
  { key: 'relations', label: '关系底物', icon: Link2 },
  { key: 'causal', label: '因果链', icon: GitBranch },
  { key: 'behavior', label: '行为图', icon: BrainCircuit },
  { key: 'engineering', label: '工程约束', icon: Wrench },
  { key: 'belief', label: '信念状态', icon: Brain },
  { key: 'subgraph', label: '编译子图', icon: GitFork },
];

// 信念条目证据计数的防御性读取 (类型之外后端可能额外返回)
function getEvidenceCount(entry: V6BeliefEntry): number | null {
  const raw = entry as unknown as Record<string, unknown>;
  if (typeof raw.evidence_count === 'number') return raw.evidence_count;
  if (typeof raw.evidence === 'number') return raw.evidence;
  return null;
}

// ─── 通用键值/层级卡片渲染 ───────────────────────────────────────────────────

function PrimitiveValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-xs text-text-muted font-mono">null</span>;
  }
  if (typeof value === 'boolean') {
    return (
      <span className={cn('text-xs font-mono', value ? 'text-status-success' : 'text-status-error')}>
        {String(value)}
      </span>
    );
  }
  if (typeof value === 'number') {
    return <span className="text-sm font-mono text-status-info">{String(value)}</span>;
  }
  const s = String(value);
  return (
    <span className="text-sm text-text-primary font-mono break-all">
      {s === '' ? '(空字符串)' : s}
    </span>
  );
}

function DataNode({ name, value, depth }: { name?: string; value: unknown; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const isObj = typeof value === 'object' && value !== null;

  if (!isObj) {
    return (
      <div className="flex items-start gap-2 py-1">
        {name !== undefined && (
          <span className="text-xs text-text-muted shrink-0 pt-0.5">{name}</span>
        )}
        <PrimitiveValue value={value} />
      </div>
    );
  }

  const isArr = Array.isArray(value);
  const entries: [string, unknown][] = isArr
    ? (value as unknown[]).map((v, i) => [String(i), v])
    : Object.entries(value as Record<string, unknown>);

  return (
    <div className="rounded-lg border border-gray-100 hover:border-gray-200 transition-colors">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left cursor-pointer"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-text-muted shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-text-muted shrink-0" />
        )}
        {name !== undefined && (
          <span className="text-xs font-medium text-text-secondary truncate">{name}</span>
        )}
        <span className="text-xs text-text-muted ml-auto shrink-0">
          {isArr ? `${entries.length} 条` : `${entries.length} 项`}
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-2 pt-1 space-y-1 border-t border-gray-50">
              {entries.length === 0 ? (
                <p className="text-xs text-text-muted py-1">{isArr ? '空列表' : '空对象'}</p>
              ) : (
                entries.map(([k, v]) => (
                  <DataNode
                    key={k}
                    name={isArr ? `#${Number(k) + 1}` : k}
                    value={v}
                    depth={depth + 1}
                  />
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function DataTree({ data }: { data: unknown }) {
  if (data === null || data === undefined) {
    return <p className="text-sm text-text-muted">暂无数据</p>;
  }
  if (typeof data !== 'object') {
    return <PrimitiveValue value={data} />;
  }
  return (
    <div className="space-y-1.5">
      <DataNode value={data} depth={0} />
    </div>
  );
}

// ─── 页面 ────────────────────────────────────────────────────────────────────

export function DeepChainPage() {
  const { relations, causal, behavior, engineering, loading, error, refresh } = useV6DeepChain();
  const [activeTab, setActiveTab] = useState<TabKey>('relations');

  // Belief 状态
  const [sessionId, setSessionId] = useState('default');
  const [belief, setBelief] = useState<V6BeliefResponse | null>(null);
  const [beliefLoading, setBeliefLoading] = useState(false);
  const [beliefError, setBeliefError] = useState<string | null>(null);

  // Subgraph 状态
  const [perspective, setPerspective] = useState<Perspective>('dialogue');
  const [subgraph, setSubgraph] = useState<V6SubgraphResponse | null>(null);
  const [subgraphLoading, setSubgraphLoading] = useState(false);
  const [subgraphError, setSubgraphError] = useState<string | null>(null);

  const loadBelief = useCallback(async (sid: string) => {
    setBeliefLoading(true);
    setBeliefError(null);
    try {
      const res = await getBelief(sid.trim() || 'default');
      setBelief(res);
    } catch (err) {
      setBelief(null);
      setBeliefError(err instanceof Error ? err.message : '获取信念数据失败');
    } finally {
      setBeliefLoading(false);
    }
  }, []);

  const loadSubgraph = useCallback(async (p: Perspective) => {
    setSubgraphLoading(true);
    setSubgraphError(null);
    try {
      const res = await getSubgraph(p);
      setSubgraph(res);
    } catch (err) {
      setSubgraph(null);
      setSubgraphError(err instanceof Error ? err.message : '获取编译子图失败');
    } finally {
      setSubgraphLoading(false);
    }
  }, []);

  const handleTabChange = useCallback(
    (key: TabKey) => {
      setActiveTab(key);
      if (key === 'belief' && belief === null && !beliefLoading) {
        loadBelief(sessionId);
      }
      if (key === 'subgraph' && subgraph === null && !subgraphLoading) {
        loadSubgraph(perspective);
      }
    },
    [belief, beliefLoading, sessionId, subgraph, subgraphLoading, perspective, loadBelief, loadSubgraph]
  );

  const handlePerspectiveChange = useCallback(
    (p: Perspective) => {
      setPerspective(p);
      loadSubgraph(p);
    },
    [loadSubgraph]
  );

  const isTreeTab = activeTab !== 'belief' && activeTab !== 'subgraph';
  const panelLoading = activeTab === 'belief' ? beliefLoading : activeTab === 'subgraph' ? subgraphLoading : loading;
  const panelError = activeTab === 'belief' ? beliefError : activeTab === 'subgraph' ? subgraphError : error;

  const handleRefresh = useCallback(() => {
    if (activeTab === 'belief') loadBelief(sessionId);
    else if (activeTab === 'subgraph') loadSubgraph(perspective);
    else refresh();
  }, [activeTab, sessionId, perspective, loadBelief, loadSubgraph, refresh]);

  const fadeIn = (delay: number) => ({
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, delay },
  });

  const getTreeData = (): V6RelationsResponse | V6CausalResponse | V6BehaviorResponse | V6EngineeringResponse | null => {
    switch (activeTab) {
      case 'relations': return relations;
      case 'causal': return causal;
      case 'behavior': return behavior;
      case 'engineering': return engineering;
      default: return null;
    }
  };

  const treeData = getTreeData();
  const treeEmpty = !treeData || Object.keys(treeData).length === 0;

  const beliefEntries = belief ? Object.entries(belief.by_hypothesis ?? {}) : [];
  const subgraphDomains = subgraph ? Object.entries(subgraph.domains ?? {}).sort((a, b) => b[1] - a[1]) : [];
  const maxDomainValue = subgraphDomains.reduce((mx, [, v]) => Math.max(mx, v), 0);

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
              <p className="text-xs text-text-muted">关系底物 · 因果链 · 行为图 · 工程约束 · 信念状态 · 编译子图</p>
            </div>
          </div>
          <button
            onClick={handleRefresh}
            disabled={panelLoading}
            className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', panelLoading && 'animate-spin')} />
            刷新
          </button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {panelError && (
          <div className="rounded-xl bg-status-error/5 text-status-error text-sm px-4 py-3">
            {panelError}
          </div>
        )}

        {/* 2026-08-18: 说明卡 — 让用户看得懂每个 tab 是干什么的 */}
        <motion.section {...fadeIn(0.02)} className="card-liquid shadow-card rounded-xl p-5">
          <div className="flex items-center gap-2 text-text-muted mb-3">
            <Brain className="h-4 w-4" />
            <span className="text-xs font-semibold">这个页面是做什么的</span>
          </div>
          <p className="text-xs text-text-secondary leading-relaxed mb-3">
            深层链是<b>认知流水线的白盒视图</b>——把对话加工过程中产生的内部知识结构
            摊开给你看（关系 / 信念 / 子图等）。各 tab 的含义:
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
            {[
              ['关系底物', '从对话中抽取的实体与关系 —— 关系是第一公民'],
              ['因果链', '因果推理链（为什么 → 所以）'],
              ['行为图', '行为模式学习（做什么、何时做、结果如何）'],
              ['工程约束', '工程模块与其约束（内部可编辑）'],
              ['信念状态', '7 维信念: 支持/冲突/稳定/覆盖/新颖/新近/熵'],
              ['编译子图', '上下文编译出的局部知识快照（给 LLM 看的）'],
            ].map(([t, d]) => (
              <div key={t} className="flex items-start gap-2 text-[11px]">
                <ChevronRight className="w-3 h-3 mt-0.5 text-primary shrink-0" />
                <span className="text-text-primary shrink-0">{t}</span>
                <span className="text-text-muted">{d}</span>
              </div>
            ))}
          </div>
        </motion.section>

        {/* Tabs */}
        <motion.div {...fadeIn(0.05)} className="flex gap-1 overflow-x-auto pb-1">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => handleTabChange(tab.key)}
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

        {/* 树形数据 Tab 面板 */}
        {isTreeTab && (
          <motion.section
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="card-liquid shadow-card rounded-xl p-5"
          >
            <div className="flex items-center gap-2 text-text-muted mb-4">
              {(() => {
                const Icon = tabs.find(t => t.key === activeTab)?.icon || Activity;
                return <Icon className="h-4 w-4" />;
              })()}
              <span className="text-xs font-semibold">{tabs.find(t => t.key === activeTab)?.label} 数据</span>
            </div>

            {treeEmpty ? (
              <div className="text-center py-16">
                <Network className="h-10 w-10 text-text-muted mx-auto mb-3" />
                <p className="text-sm text-text-secondary">暂无数据</p>
                <p className="text-xs text-text-muted mt-1">后端可能尚未实现此端点</p>
              </div>
            ) : (
              <DataTree data={treeData} />
            )}
          </motion.section>
        )}

        {/* Belief 面板 */}
        {activeTab === 'belief' && (
          <motion.section
            key="belief"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="card-liquid shadow-card rounded-xl p-5 space-y-4"
          >
            <div className="flex items-center gap-2 text-text-muted">
              <Brain className="h-4 w-4" />
              <span className="text-xs font-semibold">贝叶斯信念 (Bayesian Belief)</span>
            </div>

            {/* session_id 查询 */}
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadBelief(sessionId)}
                placeholder="session_id"
                className="w-56 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-2 text-sm text-text-primary font-mono focus:outline-none focus:border-primary"
              />
              <button
                onClick={() => loadBelief(sessionId)}
                disabled={beliefLoading}
                className="flex items-center gap-1.5 rounded-lg bg-primary text-white px-3 py-2 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
              >
                <Search className="h-3.5 w-3.5" />
                {beliefLoading ? '查询中...' : '查询'}
              </button>
            </div>

            {belief ? (
              <>
                {/* 概览统计 */}
                <div className="grid grid-cols-3 gap-2">
                  <div className="rounded-lg border border-gray-200 p-3">
                    <span className="text-xs text-text-muted">假设总数</span>
                    <p className="text-lg font-semibold text-text-primary">{belief.total_hypotheses}</p>
                  </div>
                  <div className="rounded-lg border border-gray-200 p-3">
                    <span className="text-xs text-text-muted">已锁定</span>
                    <p className="text-lg font-semibold text-text-primary">{belief.locked}</p>
                  </div>
                  <div className="rounded-lg border border-gray-200 p-3">
                    <span className="text-xs text-text-muted">平均证据</span>
                    <p className="text-lg font-semibold text-text-primary">{belief.avg_evidence.toFixed(2)}</p>
                  </div>
                </div>

                {/* 信念条目 */}
                {beliefEntries.length > 0 ? (
                  <div className="space-y-2">
                    {beliefEntries.map(([name, entry]) => {
                      const pct = Math.round(Math.min(Math.max(entry.posterior, 0), 1) * 100);
                      const evidenceCount = getEvidenceCount(entry);
                      return (
                        <div key={name} className="rounded-lg border border-gray-100 p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-sm font-medium text-text-primary truncate">{name}</span>
                            {entry.locked ? (
                              <span className="flex items-center gap-1 text-xs font-medium px-1.5 py-0.5 rounded bg-status-success/10 text-status-success shrink-0">
                                <Lock className="h-3 w-3" />
                                已锁定
                              </span>
                            ) : (
                              <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-surface-sidebar text-text-muted shrink-0">
                                未锁定
                              </span>
                            )}
                            {evidenceCount !== null && (
                              <span className="text-xs text-text-muted shrink-0">证据 {evidenceCount}</span>
                            )}
                            <span className="text-xs font-mono text-text-primary ml-auto shrink-0">{pct}%</span>
                          </div>
                          <div className="h-1.5 rounded-full bg-surface-sidebar overflow-hidden">
                            <div
                              className={cn(
                                'h-full rounded-full transition-all',
                                entry.locked ? 'bg-status-success' : 'bg-primary'
                              )}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-sm text-text-muted py-2">该会话暂无信念条目</p>
                )}
              </>
            ) : (
              !beliefLoading && (
                <div className="text-center py-16">
                  <Brain className="h-10 w-10 text-text-muted mx-auto mb-3" />
                  <p className="text-sm text-text-secondary">暂无信念数据</p>
                  <p className="text-xs text-text-muted mt-1">输入 session_id 后点击查询</p>
                </div>
              )
            )}
          </motion.section>
        )}

        {/* Subgraph 面板 */}
        {activeTab === 'subgraph' && (
          <motion.section
            key="subgraph"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="card-liquid shadow-card rounded-xl p-5 space-y-4"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-text-muted">
                <GitFork className="h-4 w-4" />
                <span className="text-xs font-semibold">编译后子图 (Compiled Subgraph)</span>
              </div>
              {/* perspective 切换 */}
              <div className="flex gap-1 rounded-lg bg-surface-sidebar p-1">
                {(['dialogue', 'meta'] as Perspective[]).map((p) => (
                  <button
                    key={p}
                    onClick={() => handlePerspectiveChange(p)}
                    className={cn(
                      'px-3 py-1 rounded-md text-xs font-medium transition-colors',
                      perspective === p
                        ? 'bg-primary text-white'
                        : 'text-text-secondary hover:text-text-primary'
                    )}
                  >
                    {p === 'dialogue' ? '对话视角' : '元视角'}
                  </button>
                ))}
              </div>
            </div>

            {subgraph ? (
              <>
                {/* 概览统计 */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <div className="rounded-lg border border-gray-200 p-3">
                    <span className="text-xs text-text-muted">视角</span>
                    <p className="text-sm font-semibold text-text-primary font-mono">{subgraph.perspective}</p>
                  </div>
                  <div className="rounded-lg border border-gray-200 p-3">
                    <span className="text-xs text-text-muted">总 Tokens</span>
                    <p className="text-lg font-semibold text-text-primary">{subgraph.total_tokens.toLocaleString()}</p>
                  </div>
                  <div className="rounded-lg border border-gray-200 p-3">
                    <span className="text-xs text-text-muted">预算</span>
                    <p className="text-lg font-semibold text-text-primary">{subgraph.budget.toLocaleString()}</p>
                  </div>
                  <div className="rounded-lg border border-gray-200 p-3">
                    <span className="text-xs text-text-muted">条目数</span>
                    <p className="text-lg font-semibold text-text-primary">{subgraph.entries.length}</p>
                  </div>
                </div>

                {/* domains 预算分配 */}
                {subgraphDomains.length > 0 && (
                  <div>
                    <div className="text-xs text-text-muted mb-2">domains 预算分配</div>
                    <div className="space-y-1.5">
                      {subgraphDomains.map(([domain, value]) => {
                        const pct = maxDomainValue > 0 ? (value / maxDomainValue) * 100 : 0;
                        return (
                          <div key={domain} className="flex items-center gap-3">
                            <span className="text-xs font-medium text-text-secondary w-28 shrink-0 truncate">{domain}</span>
                            <div className="flex-1 h-1.5 rounded-full bg-surface-sidebar overflow-hidden">
                              <div
                                className="h-full rounded-full bg-primary/70 transition-all"
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <span className="text-xs text-text-muted font-mono shrink-0">{value.toLocaleString()}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 条目列表 */}
                {subgraph.entries.length > 0 ? (
                  <div>
                    <div className="text-xs text-text-muted mb-2">条目 ({subgraph.entries.length})</div>
                    <div className="space-y-2">
                      {subgraph.entries.map((entry, idx) => (
                        <div key={idx} className="rounded-lg border border-gray-100 p-3">
                          <span className="inline-block text-xs font-medium px-1.5 py-0.5 rounded bg-primary/10 text-primary mb-1">
                            {entry.domain}
                          </span>
                          <p className="text-sm text-text-secondary break-all">{entry.content}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-text-muted py-2">该视角下暂无子图条目</p>
                )}
              </>
            ) : (
              !subgraphLoading && (
                <div className="text-center py-16">
                  <GitFork className="h-10 w-10 text-text-muted mx-auto mb-3" />
                  <p className="text-sm text-text-secondary">暂无编译子图数据</p>
                  <p className="text-xs text-text-muted mt-1">后端可能尚未实现此端点</p>
                </div>
              )
            )}
          </motion.section>
        )}

        {/* 树形 Tab 统计摘要 */}
        {isTreeTab && treeData && !treeEmpty && (
          <motion.div {...fadeIn(0.15)} className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="card-liquid shadow-card rounded-lg p-3">
              <span className="text-xs text-text-muted">顶层键</span>
              <p className="text-lg font-semibold text-text-primary">{Object.keys(treeData).length}</p>
            </div>
            <div className="card-liquid shadow-card rounded-lg p-3">
              <span className="text-xs text-text-muted">嵌套层数</span>
              <p className="text-lg font-semibold text-text-primary">{getDepth(treeData)}</p>
            </div>
            <div className="card-liquid shadow-card rounded-lg p-3">
              <span className="text-xs text-text-muted">总节点数</span>
              <p className="text-lg font-semibold text-text-primary">{getNodeCount(treeData)}</p>
            </div>
            <div className="card-liquid shadow-card rounded-lg p-3">
              <span className="text-xs text-text-muted">数组项</span>
              <p className="text-lg font-semibold text-text-primary">{getArrayCount(treeData)}</p>
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
  if (Array.isArray(data)) return data.reduce<number>((sum, v) => sum + getNodeCount(v), 1);
  return Object.values(data as Record<string, unknown>).reduce<number>((sum, v) => sum + getNodeCount(v), 1);
}

function getArrayCount(data: unknown): number {
  if (Array.isArray(data)) return data.length + data.reduce<number>((sum, v) => sum + getArrayCount(v), 0);
  if (data !== null && typeof data === 'object') {
    return Object.values(data as Record<string, unknown>).reduce<number>((sum, v) => sum + getArrayCount(v), 0);
  }
  return 0;
}
