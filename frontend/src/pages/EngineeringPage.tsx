// FILE: src/pages/EngineeringPage.tsx
// 工程链工作台: 递归地图 + 工程模块 + 约束编辑

import { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Workflow,
  RefreshCw,
  FolderTree,
  Boxes,
  Pencil,
  Save,
  UnfoldVertical,
  FoldVertical,
  Activity,
  ChevronRight,
  Lock,
} from 'lucide-react';
import {
  getRecursiveMap,
  controlRecursiveMap,
  getEngineeringModules,
  editEngineeringConstraints,
  getEngineering,
  getTools,
  getSkills,
} from '../api/v6';
import type {
  V6RecursiveMapResponse,
  V6EngineeringModule,
  V6EngineeringConstraintEditRequest,
  V6EngineeringResponse,
  V6ToolsResponse,
  V6SkillsResponse,
} from '../types/api';
import { Toast } from '../components/ui/Toast';
import { cn } from '../lib/utils';
import { useUIStore } from '@/stores/uiStore';

interface ToastState {
  type: 'success' | 'error';
  message: string;
}

// 后端可能在类型之外额外返回约束列表/数量,做防御性读取
function getModuleConstraintCount(m: V6EngineeringModule): number | null {
  const raw = m as unknown as Record<string, unknown>;
  if (Array.isArray(raw.constraints)) return raw.constraints.length;
  if (typeof raw.constraint_count === 'number') return raw.constraint_count;
  return null;
}

function getModuleStatus(m: V6EngineeringModule): string {
  const raw = m as unknown as Record<string, unknown>;
  return typeof raw.status === 'string' ? raw.status : '已加载';
}

export function EngineeringPage() {
  const [map, setMap] = useState<V6RecursiveMapResponse | null>(null);
  const [modules, setModules] = useState<V6EngineeringModule[]>([]);
  const [engineering, setEngineering] = useState<V6EngineeringResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 节点展开状态 (来自 controlRecursiveMap 响应)
  const [nodeStates, setNodeStates] = useState<Record<string, boolean>>({});
  const [nodePending, setNodePending] = useState<string | null>(null);

  // 约束编辑表单
  const [formName, setFormName] = useState('');
  const [formAction, setFormAction] = useState<V6EngineeringConstraintEditRequest['action']>('add_constraint');
  const [formConstraint, setFormConstraint] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // 2026-08-17: 工具/技能白盒视图（含下载渠道状态）
  const [tools, setTools] = useState<V6ToolsResponse | null>(null);
  const [skills, setSkills] = useState<V6SkillsResponse | null>(null);
  // 2026-08-18: 工程模块滚动增量加载（不一次性渲染全部）
  const [visibleModules, setVisibleModules] = useState(10);
  const MODULE_STEP = 10;
  const moduleLoadMoreRef = useRef<HTMLDivElement>(null);
  const openSidePanel = useUIStore((s) => s.openSidePanel);
  const setInspectNode = useUIStore((s) => s.setInspectNode);
  const setDockContent = useUIStore((s) => s.setDockContent);

  useEffect(() => {
    const el = moduleLoadMoreRef.current;
    if (!el || modules.length <= visibleModules) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setVisibleModules((c) => Math.min(c + MODULE_STEP, modules.length));
        }
      },
      { rootMargin: '200px' }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [modules.length, visibleModules]);

  const [toast, setToast] = useState<ToastState | null>(null);

  const refreshMap = useCallback(async () => {
    const m = await getRecursiveMap().catch(() => null);
    setMap(m);
    return m;
  }, []);

  const refreshModules = useCallback(async () => {
    const res = await getEngineeringModules().catch(() => null);
    setModules(res?.modules ?? []);
    return res;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [mapRes, modulesRes, engRes, toolsRes, skillsRes] = await Promise.all([
          getRecursiveMap().catch(() => null),
          getEngineeringModules().catch(() => null),
          getEngineering().catch(() => null),
          getTools().catch(() => null),
          getSkills().catch(() => null),
        ]);
        if (cancelled) return;
        setMap(mapRes);
        setModules(modulesRes?.modules ?? []);
        setEngineering(engRes);
        setTools(toolsRes);
        setSkills(skillsRes);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '获取工程链数据失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleRefresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mapRes, modulesRes, engRes, toolsRes, skillsRes] = await Promise.all([
        getRecursiveMap().catch(() => null),
        getEngineeringModules().catch(() => null),
        getEngineering().catch(() => null),
        getTools().catch(() => null),
        getSkills().catch(() => null),
      ]);
      setMap(mapRes);
      setModules(modulesRes?.modules ?? []);
      setEngineering(engRes);
      setTools(toolsRes);
      setSkills(skillsRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取工程链数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleControl = useCallback(
    async (node: string, action: 'expand' | 'collapse') => {
      setNodePending(node);
      try {
        const res = await controlRecursiveMap({ node, action });
        setNodeStates(prev => ({ ...prev, [res.node]: res.expanded }));
        await refreshMap();
      } catch (err) {
        setToast({
          type: 'error',
          message: err instanceof Error ? err.message : `节点 ${node} ${action === 'expand' ? '展开' : '折叠'}失败`,
        });
      } finally {
        setNodePending(null);
      }
    },
    [refreshMap]
  );

  const handleSelectModule = useCallback((name: string) => {
    setFormName(name);
  }, []);

  // 2026-08-17: 点击模块 → 右屏摘要（拓扑对话: 工程约束在副屏展开）
  const handleInspectModule = useCallback((m: V6EngineeringModule) => {
    const raw = m as unknown as Record<string, unknown>;
    setInspectNode({
      id: m.name,
      label: m.name,
      type: String(m.type || 'module'),
      summary: `工程模块 ${m.name} — 类型 ${m.type ?? '未知'}`,
      state: {
        constraints: raw.constraints ?? undefined,
        constraint_count: raw.constraint_count ?? undefined,
        status: raw.status ?? '已加载',
      },
    });
    openSidePanel();
    // 2026-08-17: 点击模块 → 副屏切到「节点详情」摘要（默认副屏已是环境信息）
    setDockContent('node_detail');
  }, [openSidePanel, setInspectNode, setDockContent]);

  const handleSubmit = useCallback(async () => {
    const name = formName.trim();
    const constraint = formConstraint.trim();
    if (!name || !constraint) {
      setToast({ type: 'error', message: '请填写模块名称与约束内容' });
      return;
    }
    setSubmitting(true);
    try {
      const req: V6EngineeringConstraintEditRequest = { name, action: formAction, constraint };
      await editEngineeringConstraints(req);
      setToast({
        type: 'success',
        message: `模块 ${name} 约束${formAction === 'add_constraint' ? '添加' : '移除'}成功`,
      });
      setFormConstraint('');
      await Promise.all([refreshModules(), getEngineering().then(setEngineering).catch(() => null)]);
    } catch (err) {
      setToast({
        type: 'error',
        message: err instanceof Error ? err.message : '约束编辑失败',
      });
    } finally {
      setSubmitting(false);
    }
  }, [formName, formAction, formConstraint, refreshModules]);

  const fadeIn = (delay: number) => ({
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, delay },
  });

  const mapLevels = map ? Object.entries(map.by_level ?? {}) : [];
  const maxLevelCount = mapLevels.reduce((mx, [, c]) => Math.max(mx, c), 0);

  const engEntries = engineering ? Object.entries(engineering) : [];

  return (
    <div className="min-h-screen bg-surface-main">
      {toast && (
        <Toast
          type={toast.type}
          message={toast.message}
          onClose={() => setToast(null)}
        />
      )}

      {/* Header */}
      <header className="bg-surface-card border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-primary flex items-center justify-center">
              <Workflow className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-text-primary">工程链工作台</h1>
              <p className="text-xs text-text-muted">递归地图 · 工程模块 · 约束编辑</p>
            </div>
          </div>
          <button
            onClick={handleRefresh}
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

        {/* 递归地图 */}
        <motion.section {...fadeIn(0.05)} className="card-liquid shadow-card rounded-xl p-5">
          <div className="flex items-center gap-2 text-text-muted mb-4">
            <FolderTree className="h-4 w-4" />
            <span className="text-xs font-semibold">递归地图</span>
          </div>

          {map ? (
            <div className="space-y-4">
              {/* 地图状态 */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div className="rounded-lg border border-gray-200 p-3">
                  <span className="text-xs text-text-muted">总节点数</span>
                  <p className="text-lg font-semibold text-text-primary">{map.total_nodes}</p>
                </div>
                <div className="rounded-lg border border-gray-200 p-3">
                  <span className="text-xs text-text-muted">已展开</span>
                  <p className="text-lg font-semibold text-text-primary">{map.expanded}</p>
                </div>
                <div className="rounded-lg border border-gray-200 p-3">
                  <span className="text-xs text-text-muted">高耦合节点</span>
                  <p className="text-lg font-semibold text-text-primary">{map.high_coupling}</p>
                </div>
                <div className="rounded-lg border border-gray-200 p-3">
                  <span className="text-xs text-text-muted">层级数</span>
                  <p className="text-lg font-semibold text-text-primary">{mapLevels.length}</p>
                </div>
              </div>

              {/* 节点树 (按层级) */}
              {mapLevels.length > 0 ? (
                <div className="space-y-1.5">
                  {mapLevels.map(([level, count]) => {
                    const expanded = nodeStates[level] ?? false;
                    const pending = nodePending === level;
                    return (
                      <div
                        key={level}
                        className="flex items-center gap-3 rounded-lg border border-gray-100 hover:border-gray-200 px-3 py-2 transition-colors"
                      >
                        <ChevronRight
                          className={cn(
                            'h-3.5 w-3.5 text-text-muted shrink-0 transition-transform',
                            expanded && 'rotate-90 text-primary'
                          )}
                        />
                        <span className="text-sm font-medium text-text-primary shrink-0">{level}</span>
                        <div className="flex-1 h-1.5 rounded-full bg-surface-sidebar overflow-hidden">
                          <div
                            className="h-full rounded-full bg-primary/70 transition-all"
                            style={{ width: maxLevelCount > 0 ? `${(count / maxLevelCount) * 100}%` : '0%' }}
                          />
                        </div>
                        <span className="text-xs text-text-muted font-mono shrink-0">{count} 节点</span>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            onClick={() => handleControl(level, 'expand')}
                            disabled={pending || expanded}
                            className="flex items-center gap-1 rounded-md border border-gray-200 px-2 py-1 text-xs text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-40"
                          >
                            <UnfoldVertical className="h-3 w-3" />
                            展开
                          </button>
                          <button
                            onClick={() => handleControl(level, 'collapse')}
                            disabled={pending || !expanded}
                            className="flex items-center gap-1 rounded-md border border-gray-200 px-2 py-1 text-xs text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-40"
                          >
                            <FoldVertical className="h-3 w-3" />
                            折叠
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-text-muted py-2">暂无层级节点数据</p>
              )}
            </div>
          ) : (
            <div className="text-center py-10">
              <FolderTree className="h-8 w-8 text-text-muted mx-auto mb-2" />
              <p className="text-sm text-text-secondary">暂无递归地图数据</p>
              <p className="text-xs text-text-muted mt-1">后端可能尚未实现此端点</p>
            </div>
          )}
        </motion.section>

        {/* 工具与技能（2026-08-18 上移: 递归地图下方） */}
        <motion.section {...fadeIn(0.1)} className="card-liquid shadow-card rounded-xl p-5">
          <div className="flex items-center gap-2 text-text-muted mb-4">
            <Boxes className="h-4 w-4" />
            <span className="text-xs font-semibold">工具与技能</span>
            <span className="text-[10px] text-text-muted ml-auto">白盒视图 · 下载渠道状态</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* 工具 */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-text-secondary">可用工具</span>
                <span className="text-[10px] text-text-muted">{tools?.total ?? '—'} 个</span>
              </div>
              {tools && tools.tools.length > 0 ? (
                <div className="max-h-56 overflow-y-auto space-y-1">
                  {tools.tools.slice(0, 30).map((t) => (
                    <div key={t.name} className="flex items-center gap-2 rounded-lg border border-gray-100 px-2.5 py-1.5">
                      <span className="text-xs font-mono text-text-primary shrink-0">{t.name}</span>
                      <span className="text-[10px] text-text-muted truncate flex-1">{t.description}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-sidebar text-text-muted shrink-0">{t.category}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text-muted py-3">暂无工具数据{tools?.error ? `（${tools.error}）` : ''}</p>
              )}
            </div>

            {/* 技能 + 渠道 */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-text-secondary">策略技能</span>
                <span className="text-[10px] text-text-muted">{skills?.total ?? '—'} 个</span>
              </div>
              {skills && skills.skills.length > 0 ? (
                <div className="max-h-40 overflow-y-auto space-y-1">
                  {skills.skills.slice(0, 20).map((s) => (
                    <div key={s.name} className="flex items-center gap-2 rounded-lg border border-gray-100 px-2.5 py-1.5">
                      <span className="text-xs font-medium text-text-primary shrink-0">{s.name}</span>
                      <span className="text-[10px] text-text-muted truncate flex-1">
                        {s.strategies.join(' / ')}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-sidebar text-text-muted shrink-0">{s.source}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text-muted py-3">暂无技能数据{skills?.error ? `（${skills.error}）` : ''}</p>
              )}

              {/* 下载渠道状态 */}
              <div className="mt-3">
                <span className="text-xs font-medium text-text-secondary block mb-1.5">下载渠道</span>
                <div className="space-y-1">
                  {(skills?.channels ?? []).map((ch) => (
                    <div key={ch.name} className="flex items-center gap-2 rounded-lg border border-gray-100 px-2.5 py-1.5">
                      <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', ch.status === 'ok' ? 'bg-status-success' : 'bg-status-warning')} />
                      <span className="text-xs font-medium text-text-primary shrink-0">{ch.source}</span>
                      <span className="text-[10px] text-text-muted truncate flex-1">
                        {ch.status === 'ok' ? `${ch.count} 项` : (ch.note ?? '待接入')}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-sidebar text-text-muted shrink-0">{ch.name}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </motion.section>

        {/* 约束编辑（2026-08-18 上移: 摘要/添加在工程模块上方） */}
        <motion.section {...fadeIn(0.15)} className="card-liquid shadow-card rounded-xl p-5">
          <div className="flex items-center gap-2 text-text-muted mb-4">
            <Pencil className="h-4 w-4" />
            <span className="text-xs font-semibold">约束编辑</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-text-muted mb-1.5">模块名称</label>
              <input
                type="text"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="选择下方模块或手动输入"
                className="w-full rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1.5">动作</label>
              <select
                value={formAction}
                onChange={(e) => setFormAction(e.target.value as V6EngineeringConstraintEditRequest['action'])}
                className="w-full rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
              >
                <option value="add_constraint">添加约束 (add_constraint)</option>
                <option value="remove_constraint">移除约束 (remove_constraint)</option>
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs text-text-muted mb-1.5">约束内容</label>
              <textarea
                value={formConstraint}
                onChange={(e) => setFormConstraint(e.target.value)}
                placeholder="例如: 耦合度不得超过 0.8"
                rows={3}
                className="w-full rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary resize-y"
              />
            </div>
          </div>

          <div className="flex items-center justify-end mt-3">
            <button
              onClick={handleSubmit}
              disabled={submitting || !formName.trim() || !formConstraint.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-primary text-white px-4 py-2 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" />
              {submitting ? '提交中...' : '提交约束'}
            </button>
          </div>
        </motion.section>

        {/* 工程约束数据摘要 */}
        <motion.section {...fadeIn(0.18)} className="card-liquid shadow-card rounded-xl p-5">
          <div className="flex items-center gap-2 text-text-muted mb-4">
            <Activity className="h-4 w-4" />
            <span className="text-xs font-semibold">工程约束数据摘要</span>
          </div>

          {engEntries.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {engEntries.map(([k, v]) => {
                const isObj = typeof v === 'object' && v !== null;
                return (
                  <div key={k} className="rounded-lg border border-gray-100 p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Lock className="h-3 w-3 text-text-muted shrink-0" />
                      <span className="text-xs font-medium text-text-muted">{k}</span>
                    </div>
                    <p className="text-sm text-text-primary font-mono break-all">
                      {isObj ? JSON.stringify(v) : String(v)}
                    </p>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-10">
              <Activity className="h-8 w-8 text-text-muted mx-auto mb-2" />
              <p className="text-sm text-text-secondary">暂无工程约束数据</p>
              <p className="text-xs text-text-muted mt-1">后端可能尚未实现此端点</p>
            </div>
          )}
        </motion.section>

        {/* 工程模块（2026-08-18 移至最底, 滚动增量加载） */}
        <motion.section {...fadeIn(0.2)} className="card-liquid shadow-card rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-text-muted">
              <Boxes className="h-4 w-4" />
              <span className="text-xs font-semibold">工程模块</span>
              <span className="text-[10px] text-text-muted">内部模块 · 可编辑约束（再开发）</span>
            </div>
            <span className="text-xs text-text-muted">共 {modules.length} 个模块</span>
          </div>

          {modules.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left">
                    <th className="py-2 pr-4 text-xs font-medium text-text-muted">模块名</th>
                    <th className="py-2 pr-4 text-xs font-medium text-text-muted">类型</th>
                    <th className="py-2 pr-4 text-xs font-medium text-text-muted">约束数</th>
                    <th className="py-2 pr-4 text-xs font-medium text-text-muted">状态</th>
                    <th className="py-2 text-xs font-medium text-text-muted text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {modules.slice(0, visibleModules).map((m) => {
                    const constraintCount = getModuleConstraintCount(m);
                    const status = getModuleStatus(m);
                    const selected = formName === m.name;
                    return (
                      <tr
                        key={m.name}
                        className={cn(
                          'border-b border-gray-50 transition-colors',
                          selected ? 'bg-primary/3' : 'hover:bg-surface-sidebar/50'
                        )}
                      >
                        <td className="py-2.5 pr-4">
                          <button
                            type="button"
                            onClick={() => handleInspectModule(m)}
                            className="font-medium text-text-primary hover:text-primary transition-colors text-left"
                            title="点击在右屏查看摘要"
                          >
                            {m.name}
                          </button>
                        </td>
                        <td className="py-2.5 pr-4">
                          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-surface-sidebar text-text-secondary">
                            {m.type}
                          </span>
                        </td>
                        <td className="py-2.5 pr-4">
                          <span className="font-mono text-text-primary">
                            {constraintCount !== null ? constraintCount : '—'}
                          </span>
                        </td>
                        <td className="py-2.5 pr-4">
                          <span className="flex items-center gap-1 text-xs text-status-success">
                            <span className="h-1.5 w-1.5 rounded-full bg-status-success" />
                            {status}
                          </span>
                        </td>
                        <td className="py-2.5 text-right">
                          <button
                            onClick={() => handleSelectModule(m.name)}
                            className={cn(
                              'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-colors',
                              selected
                                ? 'bg-primary text-white'
                                : 'border border-gray-200 text-text-secondary hover:text-primary hover:border-primary/30'
                            )}
                          >
                            <Pencil className="h-3 w-3" />
                            {selected ? '编辑中' : '编辑约束'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {modules.length > visibleModules && (
                <div
                  ref={moduleLoadMoreRef}
                  className="flex items-center justify-center py-3 text-xs text-text-muted"
                >
                  滚动加载更多…（{visibleModules}/{modules.length}）
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-10">
              <Boxes className="h-8 w-8 text-text-muted mx-auto mb-2" />
              <p className="text-sm text-text-secondary">暂无工程模块</p>
              <p className="text-xs text-text-muted mt-1">后端可能尚未实现此端点</p>
            </div>
          )}
        </motion.section>
      </div>
    </div>
  );
}
