/** RightDock 候选内容 — 三屏结构中右栏可切换的各类上下文面板。 */
import { useState, useEffect } from 'react';
import type { FC, ReactNode } from 'react';
import { RefreshCw, Loader2, AlertTriangle, Radar } from 'lucide-react';
import { CognitiveRadarChart } from '../CognitiveRadarChart';
import { MetricCards } from '../MetricCards';
import { useV6Profile } from '../../hooks/useV6Profile';
import { getContext, getEngineering, submitCompressionFeedback, getHeuristics, getChangelog, interveneChangelog } from '../../api/v6';
import { useTaskGraphStore } from '../../stores/taskStore';
import { useUIStore } from '../../stores/uiStore';
import { cn } from '../../lib/utils';
import type { V6HeuristicsResponse, V6ChangelogResponse, V6ChangelogEvent } from '../../types/api';

/* ── 通用面板骨架 ─────────────────────────────────────────── */

/* P0-C: 内层标题头移除 — RightDock 外壳头部已统一渲染标题（原先双头并列是右栏凌乱的主因）。
   title 保留在 props 类型中，避免改动全部调用点。 */
export const DockPanel: FC<{ title: string; children: ReactNode }> = ({ children }) => (
  <div className="flex-1 flex flex-col overflow-hidden">
    <div className="flex-1 overflow-y-auto px-4 pt-2 pb-4 space-y-4 scrollbar-hide">{children}</div>
  </div>
);

export const DockEmpty: FC<{ text: string }> = ({ text }) => (
  <div className="flex items-center justify-center h-full text-xs text-text-muted px-4 py-8">{text}</div>
);

export const DockError: FC<{ text: string }> = ({ text }) => (
  <div className="flex items-center gap-2 text-xs text-status-error px-4 py-6">
    <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
    {text}
  </div>
);

/* ── NodeDetail（右键"在右侧显示详情", B5） ────────────────── */

export function NodeDetailDockContent() {
  const node = useUIStore((s) => s.inspectNode);
  const closeDock = () => {
    useUIStore.getState().closeSidePanel();
    useUIStore.getState().closeCenterPanel();
  };
  if (!node) {
    return (
      <DockPanel title="节点详情">
        <DockEmpty text="未选择节点 — 在图谱页右键节点 → 在右侧显示详情" />
      </DockPanel>
    );
  }
  const rows: { k: string; v: string }[] = [
    { k: 'ID', v: node.id },
    { k: '类型', v: node.type || '—' },
    { k: '意图', v: node.intent || '—' },
    { k: '层级', v: node.depth != null ? String(node.depth) : '—' },
    { k: '温度', v: node.temperature || '—' },
    { k: 'EDU 数', v: node.size != null ? String(node.size) : '—' },
  ];
  return (
    <DockPanel title="节点详情">
      <div className="text-sm font-semibold text-text-primary break-words">
        {node.label || node.id}
      </div>
      <div className="space-y-1.5">
        {rows.map((r) => (
          <div key={r.k} className="flex justify-between gap-2 text-xs">
            <span className="text-text-muted shrink-0">{r.k}</span>
            <span className="text-text-secondary font-mono text-right break-all">{r.v}</span>
          </div>
        ))}
      </div>
      {(node.entities?.length ?? 0) > 0 && (
        <div>
          <div className="text-xs font-semibold text-text-primary mb-1">实体</div>
          <div className="flex flex-wrap gap-1">
            {node.entities!.map((e, i) => (
              <span key={i} className="px-1.5 py-0.5 rounded bg-primary/10 text-primary text-[10px]">
                {e}
              </span>
            ))}
          </div>
        </div>
      )}
      {node.raw_text && (
        <div>
          <div className="text-xs font-semibold text-text-primary mb-1">原文</div>
          <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap break-words">
            {node.raw_text}
          </p>
        </div>
      )}
      {node.summary && (
        <div>
          <div className="text-xs font-semibold text-text-primary mb-1">摘要</div>
          <p className="text-xs text-text-secondary leading-relaxed break-words">{node.summary}</p>
        </div>
      )}
      {(node.edges?.length ?? 0) > 0 && (
        <div>
          <div className="text-xs font-semibold text-text-primary mb-1">关联边</div>
          <div className="space-y-1">
            {node.edges!.map((e, i) => (
              <div key={i} className="text-[11px] text-text-muted font-mono break-all">
                {e.source.slice(0, 12)} → {e.target.slice(0, 12)}
                {e.type ? ` [${e.type}]` : ''}
              </div>
            ))}
          </div>
        </div>
      )}
      {node.state && Object.keys(node.state).length > 0 && (
        <div>
          <div className="text-xs font-semibold text-text-primary mb-1">State</div>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {Object.entries(node.state).map(([k, v]) => (
              <div key={k} className="flex justify-between text-[11px]">
                <span className="text-text-muted">{k}</span>
                <span className="text-text-secondary font-mono truncate max-w-[180px]">
                  {typeof v === 'string' ? v : JSON.stringify(v)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={closeDock}
        className="w-full px-3 py-1.5 rounded-md bg-surface-card border border-subtle text-xs text-text-secondary hover:text-text-primary hover:bg-surface-card-hover transition-colors"
      >
        关闭
      </button>
    </DockPanel>
  );
}

/* ── Profile（认知画像, 原 RightPanel 主体） ───────────────── */

export function ProfileDockContent() {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const { profile, loading, refresh } = useV6Profile(true, 5000);

  const radarData = profile
    ? Object.entries(profile?.oceAN_dims ?? {}).map(([k, v]) => ({
        dimension: k,
        value: Math.round(v * 100),
        fullMark: 100,
      }))
    : undefined;

  const metricCards = profile
    ? Object.entries(profile?.oceAN_dims ?? {})
        .sort(([, a], [, b]) => (b as number) - (a as number))
        .slice(0, 3)
        .map(([k, v]) => ({
          label: k,
          value: Math.round((v as number) * 100),
          trend: 0,
        }))
    : undefined;

  const handleRefresh = () => {
    setIsRefreshing(true);
    refresh();
    setTimeout(() => setIsRefreshing(false), 800);
  };

  // 空态判定看维度数据本身:后端离线(profile=null)与首次使用(oceAN_dims 为空对象)统一走空态
  const hasDims = !!profile && Object.keys(profile.oceAN_dims ?? {}).length > 0;

  return (
    <DockPanel title="认知画像">
      {!hasDims && loading ? (
        <div className="flex justify-center py-10">
          <Loader2 className="w-4 h-4 animate-spin text-text-muted" />
        </div>
      ) : !hasDims ? (
        /* 去示范数据:第一次使用/后端未连接 — 诚实空态, 不放假数值 */
        <div className="flex flex-col items-center justify-center py-10 text-center">
          <div className="w-10 h-10 rounded-full bg-surface-card border border-subtle flex items-center justify-center mb-3">
            <Radar className="w-4 h-4 text-text-muted" />
          </div>
          <p className="text-xs text-text-muted">暂无画像数据</p>
          <p className="text-[11px] text-text-muted mt-1 leading-relaxed">
            开始对话后,这里会展示认知维度分析
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-col items-center">
            <CognitiveRadarChart data={radarData} size={200} />
          </div>
          <MetricCards metrics={metricCards} />
        </>
      )}
      {/* 成功/风险状态卡移除:无后端数据源(见 UI_REFACTOR_PLAN B6) */}
      <div className="pt-2 border-t border-hairline flex items-center justify-between">
        <span className="text-xs text-text-muted">实时认知维度分析</span>
        <button
          type="button"
          onClick={handleRefresh}
          className="p-1.5 rounded-md hover:bg-surface-card-hover transition-colors"
          aria-label="刷新画像"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-text-muted ${isRefreshing || loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
    </DockPanel>
  );
}

/* ── Context（上下文视图, /v6/context） ───────────────────── */

export function ContextDockContent() {
  const [data, setData] = useState<{ intent_category?: string; entries?: unknown[]; total_tokens?: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quality, setQuality] = useState<'good' | 'bad' | null>(null);
  const [comment, setComment] = useState('');
  const [feedbackSent, setFeedbackSent] = useState<boolean | null>(null);

  const load = () => {
    setLoading(true);
    getContext()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const submitFeedback = () => {
    if (!quality) return;
    submitCompressionFeedback({ quality, comment })
      .then((r) => setFeedbackSent(r.recorded))
      .catch(() => setFeedbackSent(false));
  };

  if (loading) return <DockPanel title="上下文"><div className="flex justify-center py-6"><Loader2 className="w-4 h-4 animate-spin text-text-muted" /></div></DockPanel>;
  if (error) return <DockPanel title="上下文"><DockError text={error} /></DockPanel>;

  const entries = (data?.entries ?? []) as { domain?: string; type?: string; content?: string; confidence?: number }[];

  return (
    <DockPanel title="上下文">
      <div className="text-xs text-text-muted">
        {data?.intent_category ? `意图域: ${data.intent_category}` : '当前会话上下文'}
        {data?.total_tokens != null && ` · ~${data.total_tokens} tokens`}
      </div>
      <div className="space-y-2">
        {entries.slice(0, 12).map((e, i) => (
          <div key={i} className="bg-surface-card rounded-lg border border-subtle p-2.5">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">{e.domain ?? '?'}</span>
              <span className="text-[10px] text-text-muted">{e.type ?? ''}</span>
              {e.confidence != null && (
                <span className="ml-auto text-[10px] text-text-muted">{Math.round(e.confidence * 100)}%</span>
              )}
            </div>
            <p className="text-xs text-text-secondary line-clamp-3 break-words">{e.content ?? ''}</p>
          </div>
        ))}
        {entries.length === 0 && <DockEmpty text="暂无上下文条目" />}
      </div>
      {/* GAP-4: 压缩质量反馈闭环 */}
      <div className="border-t border-hairline pt-3">
        <div className="text-xs text-text-muted mb-2">压缩质量反馈</div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => { setQuality('good'); setFeedbackSent(null); }}
            className={cn(
              'px-2.5 py-1 rounded border text-xs transition-colors',
              quality === 'good'
                ? 'bg-status-success/10 border-status-success text-status-success'
                : 'border-subtle text-text-secondary hover:bg-surface-card-hover'
            )}
          >
            👍 不错
          </button>
          <button
            type="button"
            onClick={() => { setQuality('bad'); setFeedbackSent(null); }}
            className={cn(
              'px-2.5 py-1 rounded border text-xs transition-colors',
              quality === 'bad'
                ? 'bg-status-error/10 border-status-error text-status-error'
                : 'border-subtle text-text-secondary hover:bg-surface-card-hover'
            )}
          >
            👎 有问题
          </button>
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="补充说明（可选）"
            className="flex-1 min-w-0 px-2 py-1 rounded border border-subtle bg-surface-card text-xs text-text-primary placeholder:text-text-muted outline-none focus:border-primary"
          />
          <button
            type="button"
            onClick={submitFeedback}
            disabled={!quality}
            className="px-2.5 py-1 rounded bg-primary text-white text-xs font-medium hover:bg-primary/90 disabled:opacity-40"
          >
            提交
          </button>
        </div>
        {feedbackSent === true && (
          <div className="text-[11px] text-status-success mt-1.5">已记录，感谢反馈（压缩阈值调优输入）</div>
        )}
        {feedbackSent === false && (
          <div className="text-[11px] text-status-error mt-1.5">反馈提交失败</div>
        )}
      </div>
    </DockPanel>
  );
}

/* ── Engineering（工程链视图, /v6/engineering） ────────────── */

export function EngineeringDockContent() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    getEngineering()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (loading) return <DockPanel title="工程链"><div className="flex justify-center py-6"><Loader2 className="w-4 h-4 animate-spin text-text-muted" /></div></DockPanel>;
  if (error) return <DockPanel title="工程链"><DockError text={error} /></DockPanel>;

  const rows = Object.entries(data ?? {}).slice(0, 14);

  return (
    <DockPanel title="工程链">
      <div className="space-y-1.5">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-start justify-between gap-2 text-xs bg-surface-card rounded-lg border border-subtle px-2.5 py-2">
            <span className="text-text-secondary break-all">{k}</span>
            <span className="text-text-muted text-[10px] shrink-0 max-w-[45%] truncate">
              {typeof v === 'object' ? JSON.stringify(v).slice(0, 60) : String(v)}
            </span>
          </div>
        ))}
        {rows.length === 0 && <DockEmpty text="暂无工程链数据" />}
      </div>
    </DockPanel>
  );
}

/* ── Tasks（任务概览, taskStore 状态） ─────────────────────── */

export function TasksDockContent() {
  const taskGraph = useTaskGraphStore();
  const nodes = taskGraph?.nodes?.length ?? 0;
  const edges = taskGraph?.edges?.length ?? 0;
  const status = taskGraph?.executionStatus ?? 'idle';

  return (
    <DockPanel title="任务">
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-surface-card rounded-lg border border-subtle p-3 text-center">
          <div className="text-lg font-semibold text-text-primary">{nodes}</div>
          <div className="text-text-muted mt-0.5">节点</div>
        </div>
        <div className="bg-surface-card rounded-lg border border-subtle p-3 text-center">
          <div className="text-lg font-semibold text-text-primary">{edges}</div>
          <div className="text-text-muted mt-0.5">连线</div>
        </div>
      </div>
      <div className="text-xs text-text-muted">
        执行状态: <span className="text-text-secondary">{String(status)}</span>
      </div>
      <p className="text-xs text-text-muted leading-relaxed">
        任务规划在「任务规划」页编辑, LLM 规划会自动沉淀。此处为当前会话任务概览。
      </p>
    </DockPanel>
  );
}

/* ── Legend（图谱图例） ───────────────────────────────────── */

export function LegendDockContent() {
  return (
    <DockPanel title="图例">
      <div className="text-xs space-y-3">
        <div>
          <div className="text-text-muted mb-1.5">节点类型</div>
          <div className="space-y-1">
            {[
              ['session', '会话块（对话/主题树）'],
              ['task', '任务节点'],
              ['concept', '概念/主题'],
            ].map(([t, d]) => (
              <div key={t} className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-primary/60 inline-block shrink-0" />
                <span className="font-medium text-text-secondary">{t}</span>
                <span className="text-text-muted">{d}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="text-text-muted mb-1.5">温度（活跃度）</div>
          <div className="space-y-1">
            {[
              ['hot', '#ef4444', '活跃'],
              ['warm', '#f59e0b', '近期使用'],
              ['cold', '#3b82f6', '冷却'],
            ].map(([t, c, d]) => (
              <div key={t} className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full inline-block shrink-0" style={{ backgroundColor: c }} />
                <span className="font-medium text-text-secondary">{t}</span>
                <span className="text-text-muted">{d}</span>
              </div>
            ))}
          </div>
        </div>
        <p className="text-text-muted leading-relaxed">
          右键节点可编辑/删除/调整温度; 双击编辑名称; 拖拽连线调整边权重。
        </p>
      </div>
    </DockPanel>
  );
}

/* ── Thinking（思考流, 待接线占位） ───────────────────────── */

export function ThinkingDockContent() {
  return (
    <DockPanel title="思考流">
      <DockEmpty text="思考流视图待接线 — 将展示 LLM 推理步骤/工具调用流（与 DeepChain 共享事件源）" />
    </DockPanel>
  );
}

/* ── Heuristics（二阶抽象启发库存, /v6/heuristics） ───────── */

const SOURCE_LABEL: Record<string, string> = {
  seed: '种子', axiom: '公理', distilled: '蒸馏', rule: '规则',
};

export function HeuristicsDockContent() {
  const [data, setData] = useState<V6HeuristicsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    getHeuristics()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (loading) return <DockPanel title="启发"><div className="flex justify-center py-6"><Loader2 className="w-4 h-4 animate-spin text-text-muted" /></div></DockPanel>;
  if (error) return <DockPanel title="启发"><DockError text={error} /></DockPanel>;

  const stats = data?.stats;
  const items = data?.heuristics ?? [];

  return (
    <DockPanel title="启发">
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-surface-card rounded-lg border border-subtle p-2.5 text-center">
          <div className="text-base font-semibold text-text-primary">{stats?.total ?? 0}</div>
          <div className="text-text-muted mt-0.5">库存（活跃 {stats?.active ?? 0}）</div>
        </div>
        <div className="bg-surface-card rounded-lg border border-subtle p-2.5 text-center">
          <div className="text-base font-semibold text-text-primary">
            {stats?.avg_coverage != null ? `${Math.round(stats.avg_coverage * 100)}%` : '—'}
          </div>
          <div className="text-text-muted mt-0.5">平均覆盖率</div>
        </div>
      </div>
      <div className="space-y-2">
        {items.map((h) => (
          <details key={h.heuristic_id} className="bg-surface-card rounded-lg border border-subtle">
            <summary className="px-2.5 py-2 text-xs text-text-primary cursor-pointer hover:text-primary">
              {h.pattern_desc}
              <span className="ml-2 text-[10px] text-text-muted">
                {SOURCE_LABEL[h.source] ?? h.source} · 覆盖 {Math.round(h.coverage * 100)}%
                {h.active ? '' : ' · 停用'}
              </span>
            </summary>
            <div className="px-2.5 pb-2.5 space-y-1 text-[11px] text-text-secondary">
              <div><span className="text-text-muted">适用: </span>{h.conditions}</div>
              <div><span className="text-text-muted">反例: </span>{h.counterexample}</div>
              <div><span className="text-text-muted">路径: </span>{h.reasoning_path}</div>
            </div>
          </details>
        ))}
        {items.length === 0 && <DockEmpty text="启发库存为空（冷启动中）" />}
      </div>
      <p className="text-[11px] text-text-muted leading-relaxed">
        启发 = 决策依据（与约束同构）; 决策时自动注入上下文。来源: 种子（人类常识）/
        蒸馏（LLM 二阶抽象）/ 规则（无 LLM 兜底）。
      </p>
    </DockPanel>
  );
}

/* ── Changelog（GAP-F1: 决策事件流, git log + PR review 语义） ── */

const KIND_LABEL: Record<string, string> = {
  strategy_switch: '策略切换', plan_gate: '关卡', meta_advice: '元认知建议',
  user_correction: '用户修正', heuristic_health: '启发活性', tool_batch: '工具批次',
};

const STATUS_STYLE: Record<string, string> = {
  proposed: 'bg-amber-500/10 text-amber-600 border-amber-300',
  applied: 'bg-status-success/10 text-status-success border-status-success/40',
  rejected: 'bg-status-error/10 text-status-error border-status-error/40',
  reverted: 'bg-gray-500/10 text-text-muted border-subtle',
};

export function ChangelogDockContent() {
  const [data, setData] = useState<V6ChangelogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState('');
  const [busy, setBusy] = useState(false);

  const load = (kind = kindFilter) => {
    setLoading(true);
    getChangelog(50, kind)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleIntervene = async (ev: V6ChangelogEvent, status: 'applied' | 'rejected') => {
    setBusy(true);
    try {
      await interveneChangelog({
        status,
        dimension: ev.dimension,
        kind: ev.kind,
        comment: status === 'applied' ? '批准（前端介入）' : '否决（前端介入）',
      });
      load();
    } catch {
      setError('介入失败');
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <DockPanel title="变更日志"><div className="flex justify-center py-6"><Loader2 className="w-4 h-4 animate-spin text-text-muted" /></div></DockPanel>;
  if (error) return <DockPanel title="变更日志"><DockError text={error} /></DockPanel>;

  const stats = data?.stats;
  const events = data?.events ?? [];

  return (
    <DockPanel title="变更日志">
      {/* 统计 + 筛选 */}
      <div className="flex items-center gap-2 text-[11px]">
        <span className="text-text-muted">事件 {stats?.total ?? 0}</span>
        {(stats?.proposed ?? 0) > 0 && (
          <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600">
            待介入 {stats?.proposed}
          </span>
        )}
        <select
          value={kindFilter}
          onChange={(e) => { setKindFilter(e.target.value); load(e.target.value); }}
          className="ml-auto px-1.5 py-0.5 rounded border border-subtle bg-surface-card text-[11px] text-text-secondary outline-none"
        >
          <option value="">全部</option>
          <option value="strategy_switch">策略切换</option>
          <option value="plan_gate">关卡</option>
          <option value="meta_advice">元认知</option>
          <option value="user_correction">用户修正</option>
        </select>
      </div>

      {/* 事件流（git log 风格） */}
      <div className="space-y-2">
        {events.map((ev, i) => {
          const status = ev.status ?? 'applied';
          return (
            <div key={`${ev.ts}-${i}`} className="bg-surface-card rounded-lg border border-subtle p-2.5 space-y-1">
              <div className="flex items-center gap-2 text-[11px]">
                <span className={cn('px-1.5 py-0.5 rounded border font-medium',
                                    STATUS_STYLE[status] ?? STATUS_STYLE.applied)}>
                  {status === 'proposed' ? '待介入' : status === 'applied' ? '已生效' : status === 'rejected' ? '已否决' : '已回退'}
                </span>
                <span className="font-medium text-text-secondary">
                  {KIND_LABEL[ev.kind] ?? ev.kind}
                </span>
                <span className="text-text-muted truncate flex-1">{ev.dimension}</span>
                <span className="text-text-muted shrink-0">
                  {new Date(ev.ts * 1000).toLocaleTimeString('zh-CN', { hour12: false })}
                </span>
              </div>
              {ev.reason && (
                <div className="text-[11px] text-text-muted">{ev.reason}</div>
              )}
              {(ev.before !== undefined || ev.after !== undefined) && (
                <div className="text-[11px] text-text-secondary font-mono truncate">
                  {ev.before !== undefined && <span className="text-status-error line-through">{_fmt(ev.before)}</span>}
                  {' → '}
                  {ev.after !== undefined && <span className="text-status-success">{_fmt(ev.after)}</span>}
                </div>
              )}
              {status === 'proposed' && (
                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleIntervene(ev, 'applied')}
                    className="px-2 py-0.5 rounded bg-status-success text-white text-[11px] font-medium hover:opacity-90 disabled:opacity-40"
                  >
                    批准
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleIntervene(ev, 'rejected')}
                    className="px-2 py-0.5 rounded bg-status-error text-white text-[11px] font-medium hover:opacity-90 disabled:opacity-40"
                  >
                    否决
                  </button>
                  <span className="text-[10px] text-text-muted">PR review 语义: 不打断执行</span>
                </div>
              )}
            </div>
          );
        })}
        {events.length === 0 && <DockEmpty text="暂无决策事件" />}
      </div>
    </DockPanel>
  );
}

function _fmt(v: unknown): string {
  if (v === null || v === undefined) return '∅';
  if (typeof v === 'string') return v.length > 60 ? `${v.slice(0, 60)}…` : v;
  if (typeof v === 'object') return JSON.stringify(v).slice(0, 80);
  return String(v);
}
