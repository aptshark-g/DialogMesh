// FILE: src/components/meta/GovernancePanel.tsx
// 运行治理白盒（2026-08-17 前端绑定）— 高可用/自修/体检/观测 8 端点
// 展示: governor 熔断 · 异步诊断 · 自修复队列 · 主动体检 · 预热 ·
// 系统自画像 · 蓝图建议 · LLM 调用观测。

import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle2,
  FileSearch,
  Gauge,
  Loader2,
  RefreshCw,
  ScanSearch,
  ShieldAlert,
  Stethoscope,
  Thermometer,
  Wrench,
  XCircle,
} from 'lucide-react';
import {
  getGovernorStats,
  getDiagnosisStats,
  getSystemProfile,
  getRepairs,
  applyRepair,
  confirmRepair,
  getProbeStats,
  runProbe,
  getWarmupStats,
  runWarmup,
  getBlueprintSuggestions,
  getLlmCalls,
} from '../../api/v6';
import type {
  V6GovernorStats,
  V6DiagnosisStats,
  V6SystemProfile,
  V6RepairsResponse,
  V6ProbeStats,
  V6WarmupStats,
  V6BlueprintSuggestions,
  V6LlmCallsResponse,
} from '../../types/api';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';
import { cn } from '../../lib/utils';

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

const fmtTs = (ts: unknown): string => {
  const n = typeof ts === 'number' ? ts : Number(ts);
  if (!Number.isFinite(n) || n <= 0) return '—';
  const ms = n < 1e12 ? n * 1000 : n;
  const d = new Date(ms);
  return Number.isNaN(d.getTime())
    ? String(ts)
    : d.toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const fmtVal = (v: unknown): string =>
  isRecord(v) || Array.isArray(v) ? JSON.stringify(v) : String(v ?? '—');

const breakerStateTone = (state: string) =>
  state === 'open'
    ? { badge: 'error' as const, text: 'text-status-error' }
    : state === 'half_open'
      ? { badge: 'warning' as const, text: 'text-status-warning' }
      : { badge: 'success' as const, text: 'text-status-success' };

function SectionCard({
  title,
  icon,
  action,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="card-liquid shadow-card rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-text-muted">
          {icon}
          <span className="text-xs font-semibold">{title}</span>
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function ErrorNote({ msg }: { msg: string }) {
  return (
    <div className="rounded-lg bg-status-error/5 text-status-error text-xs px-3 py-2">
      {msg}
    </div>
  );
}

export function GovernancePanel() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [governor, setGovernor] = useState<V6GovernorStats | null>(null);
  const [diagnosis, setDiagnosis] = useState<V6DiagnosisStats | null>(null);
  const [profile, setProfile] = useState<V6SystemProfile | null>(null);
  const [repairs, setRepairs] = useState<V6RepairsResponse | null>(null);
  const [probe, setProbe] = useState<V6ProbeStats | null>(null);
  const [warmup, setWarmup] = useState<V6WarmupStats | null>(null);
  const [blueprint, setBlueprint] = useState<V6BlueprintSuggestions | null>(null);
  const [llmCalls, setLlmCalls] = useState<V6LlmCallsResponse | null>(null);

  const [busyRepair, setBusyRepair] = useState<string | null>(null);
  const [probeRunning, setProbeRunning] = useState(false);
  const [warmupRunning, setWarmupRunning] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        gov, diag, prof, rep, prb, wm, bp, calls,
      ] = await Promise.all([
        getGovernorStats().catch(() => null),
        getDiagnosisStats().catch(() => null),
        getSystemProfile().catch(() => null),
        getRepairs().catch(() => null),
        getProbeStats().catch(() => null),
        getWarmupStats().catch(() => null),
        getBlueprintSuggestions().catch(() => null),
        getLlmCalls().catch(() => null),
      ]);
      if (!gov && !diag && !prof) {
        setError('无法连接治理白盒,请检查 DialogMesh API 是否运行');
      }
      setGovernor(gov);
      setDiagnosis(diag);
      setProfile(prof);
      setRepairs(rep);
      setProbe(prb);
      setWarmup(wm);
      setBlueprint(bp);
      setLlmCalls(calls);
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取治理数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => clearInterval(timer);
  }, [refresh]);

  const handleApplyRepair = useCallback(async (id: string) => {
    setBusyRepair(id);
    try {
      await applyRepair(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : '应用修复失败');
    } finally {
      setBusyRepair(null);
    }
  }, [refresh]);

  const handleConfirmRepair = useCallback(async (id: string, passed: boolean) => {
    setBusyRepair(id);
    try {
      await confirmRepair(id, passed);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : '回写验证结果失败');
    } finally {
      setBusyRepair(null);
    }
  }, [refresh]);

  const handleRunProbe = useCallback(async () => {
    setProbeRunning(true);
    try {
      await runProbe();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : '触发体检失败');
    } finally {
      setProbeRunning(false);
    }
  }, [refresh]);

  const handleRunWarmup = useCallback(async () => {
    setWarmupRunning(true);
    try {
      await runWarmup();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : '触发预热失败');
    } finally {
      setWarmupRunning(false);
    }
  }, [refresh]);

  const openBreakers = (governor?.breakers ?? []).filter((b) => b.state === 'open');

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-xl bg-status-error/5 text-status-error text-sm px-4 py-3">
          {error}
        </div>
      )}

      {/* 概览条: 熔断 / 诊断 / 修复 / 体检 / 预热 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {loading && !governor ? (
          Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} height={84} className="rounded-xl" />
          ))
        ) : (
          <>
            <div className="card-liquid shadow-card rounded-xl p-4">
              <div className="text-xs text-text-muted">熔断器</div>
              <div className={cn('mt-1 text-2xl font-semibold',
                openBreakers.length > 0 ? 'text-status-error' : 'text-text-primary')}>
                {governor ? `${openBreakers.length}/${governor.breakers.length}` : '—'}
              </div>
              <div className="text-[10px] text-text-muted">在飞 {governor?.in_flight ?? '—'}</div>
            </div>
            <div className="card-liquid shadow-card rounded-xl p-4">
              <div className="text-xs text-text-muted">诊断队列</div>
              <div className={cn('mt-1 text-2xl font-semibold',
                (diagnosis?.pending ?? 0) > 0 ? 'text-status-warning' : 'text-text-primary')}>
                {diagnosis?.pending ?? '—'}
              </div>
              <div className="text-[10px] text-text-muted">
                报告 {diagnosis?.reports?.length ?? '—'}
              </div>
            </div>
            <div className="card-liquid shadow-card rounded-xl p-4">
              <div className="text-xs text-text-muted">修复包</div>
              <div className="mt-1 text-2xl font-semibold text-text-primary">
                {repairs?.repairs?.length ?? '—'}
              </div>
              <div className="text-[10px] text-text-muted">
                待审 {(repairs?.repairs ?? []).filter((r) => r.status === 'pending').length}
              </div>
            </div>
            <div className="card-liquid shadow-card rounded-xl p-4">
              <div className="text-xs text-text-muted">主动体检</div>
              <div className={cn('mt-1 text-2xl font-semibold',
                probe?.running ? 'text-status-info' : 'text-text-primary')}>
                {probe ? (probe.running ? '运行中' : `${probe.runs} 次`) : '—'}
              </div>
              <div className="text-[10px] text-text-muted">
                下次 {probe?.next_due_in_s != null ? `${probe.next_due_in_s}s` : '—'}
              </div>
            </div>
            <div className="card-liquid shadow-card rounded-xl p-4">
              <div className="text-xs text-text-muted">预热</div>
              <div className={cn('mt-1 text-2xl font-semibold',
                warmup?.running ? 'text-status-info' : 'text-text-primary')}>
                {warmup ? (warmup.running ? '运行中' : `${warmup.runs} 次`) : '—'}
              </div>
              <div className="text-[10px] text-text-muted">预算 {warmup?.budget_s ?? '—'}s</div>
            </div>
          </>
        )}
      </div>

      <div className="flex justify-end">
        <button
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
          刷新
        </button>
      </div>

      {/* ── 治理: 熔断状态 ── */}
      <SectionCard
        title="链路治理 ExecutionGovernor"
        icon={<ShieldAlert className="h-4 w-4" />}
      >
        {!governor ? (
          loading ? <Skeleton height={90} className="rounded-lg" /> : <ErrorNote msg="governor 无数据" />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {governor.breakers.length === 0 ? (
              <div className="text-xs text-text-muted col-span-full">暂无熔断器（未发生调用）</div>
            ) : (
              governor.breakers.map((b) => {
                const tone = breakerStateTone(b.state);
                return (
                  <div key={b.scope} className="rounded-lg bg-surface-sidebar border border-subtle p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-text-secondary">{b.scope}</span>
                      <Badge variant="status" color={tone.badge}>{b.state}</Badge>
                    </div>
                    <div className="flex flex-wrap gap-x-3 text-[10px] text-text-muted">
                      <span>连败 <span className={cn('font-mono', tone.text)}>{b.consecutive_failures}</span></span>
                      <span>调用 <span className="font-mono text-text-secondary">{b.total_calls}</span></span>
                      <span>失败 <span className="font-mono text-text-secondary">{b.total_failures}</span></span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
        {governor && governor.recent_actions.length > 0 && (
          <div className="mt-3">
            <div className="text-[10px] text-text-muted mb-1.5">最近治理动作</div>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {governor.recent_actions.slice(-10).map((a, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]">
                  <span className="text-text-muted shrink-0">{fmtTs(a.ts)}</span>
                  <span className="font-mono text-text-secondary shrink-0">{String(a.action ?? '?')}</span>
                  <span className="text-text-muted truncate">{String(a.scope ?? '')} {String(a.reason ?? '')}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </SectionCard>

      {/* ── 诊断 + 自修 ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard
          title="异步诊断 A10 大环"
          icon={<Stethoscope className="h-4 w-4" />}
        >
          {!diagnosis ? (
            loading ? <Skeleton height={90} className="rounded-lg" /> : <ErrorNote msg="diagnosis 无数据" />
          ) : diagnosis.reports.length === 0 ? (
            <div className="text-xs text-text-muted">暂无诊断报告（失败信号 → 自动诊断后此处可见）</div>
          ) : (
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {diagnosis.reports.slice().reverse().map((r, i) => {
                const rid = String(r.id ?? i);
                return (
                  <div key={rid} className="rounded-lg bg-surface-sidebar border border-subtle p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[11px] text-text-muted">{fmtTs(r.ts)}</span>
                      <span className="flex items-center gap-1 text-[11px] text-text-secondary">
                        {r.self_adjusted ? (
                          <CheckCircle2 className="h-3 w-3 text-status-success" />
                        ) : (
                          <Activity className="h-3 w-3" />
                        )}
                        {(r.confidence ?? 0) > 0 ? `置信 ${Math.round(Number(r.confidence) * 100)}%` : ''}
                      </span>
                    </div>
                    <div className="text-xs font-medium text-text-primary">{String(r.root_cause ?? '?')}</div>
                    <div className="text-[11px] text-text-muted mt-0.5">trigger: {String(r.trigger ?? '—')}</div>
                  </div>
                );
              })}
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="自修复队列 SelfRepair"
          icon={<Wrench className="h-4 w-4" />}
        >
          {!repairs ? (
            loading ? <Skeleton height={90} className="rounded-lg" /> : <ErrorNote msg="repairs 无数据" />
          ) : repairs.repairs.length === 0 ? (
            <div className="text-xs text-text-muted">暂无修复包</div>
          ) : (
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {repairs.repairs.map((r) => (
                <div key={r.id} className="rounded-lg bg-surface-sidebar border border-subtle p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-mono text-text-secondary break-all">{r.id.slice(0, 18)}</span>
                    <Badge variant="status"
                      color={r.status === 'applied' ? 'success' : r.status === 'failed' ? 'error' : 'warning'}>
                      {r.status}
                    </Badge>
                  </div>
                  <div className="text-xs text-text-primary">{r.summary ?? r.reason ?? '—'}</div>
                  <div className="text-[10px] text-text-muted mt-0.5">source: {r.source ?? '—'}</div>
                  {r.status === 'pending' && (
                    <div className="flex gap-1.5 mt-2">
                      <button
                        onClick={() => void handleApplyRepair(r.id)}
                        disabled={busyRepair === r.id}
                        className="flex items-center gap-1 rounded-md bg-primary px-2 py-1 text-[11px] font-medium text-white disabled:opacity-50"
                      >
                        {busyRepair === r.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wrench className="h-3 w-3" />}
                        应用
                      </button>
                      <button
                        onClick={() => void handleConfirmRepair(r.id, true)}
                        disabled={busyRepair === r.id}
                        className="flex items-center gap-1 rounded-md bg-surface-sidebar border border-subtle px-2 py-1 text-[11px] text-text-secondary disabled:opacity-50"
                      >
                        <CheckCircle2 className="h-3 w-3" />
                        验证通过
                      </button>
                      <button
                        onClick={() => void handleConfirmRepair(r.id, false)}
                        disabled={busyRepair === r.id}
                        className="flex items-center gap-1 rounded-md bg-surface-sidebar border border-subtle px-2 py-1 text-[11px] text-status-error disabled:opacity-50"
                      >
                        <XCircle className="h-3 w-3" />
                        验证失败
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      {/* ── 体检 + 预热 ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard
          title="主动体检 ProactiveHealthProbe"
          icon={<ScanSearch className="h-4 w-4" />}
          action={
            <button
              onClick={() => void handleRunProbe()}
              disabled={probeRunning || probe?.running}
              className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
            >
              {probeRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Gauge className="h-3.5 w-3.5" />}
              立即巡检
            </button>
          }
        >
          {!probe ? (
            loading ? <Skeleton height={90} className="rounded-lg" /> : <ErrorNote msg="probe 无数据" />
          ) : (
            <>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted mb-3">
                <span>周期 {probe.interval_s}s</span>
                <span>启动延迟 {probe.startup_delay_s}s</span>
                <span>最近 {fmtTs(probe.last_run)}</span>
                <span>下次 {probe.next_due_in_s != null ? `${probe.next_due_in_s}s` : '—'}</span>
              </div>
              {probe.history.length === 0 ? (
                <div className="text-xs text-text-muted">暂无巡检历史</div>
              ) : (
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {probe.history.slice().reverse().map((h, i) => (
                    <div key={i} className="flex items-center gap-2 text-[11px]">
                      <span className="text-text-muted shrink-0">{fmtTs(h.ts)}</span>
                      {h.skipped ? (
                        <span className="text-text-muted">skipped</span>
                      ) : (
                        <span className="flex items-center gap-1 text-text-secondary">
                          <CheckCircle2 className="h-3 w-3 text-status-success" />
                          {Array.isArray(h.findings) ? `${h.findings.length} findings` : 'run'}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </SectionCard>

        <SectionCard
          title="启动预热 Warmup"
          icon={<Thermometer className="h-4 w-4" />}
          action={
            <button
              onClick={() => void handleRunWarmup()}
              disabled={warmupRunning || warmup?.running}
              className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
            >
              {warmupRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Activity className="h-3.5 w-3.5" />}
              触发预热
            </button>
          }
        >
          {!warmup ? (
            loading ? <Skeleton height={90} className="rounded-lg" /> : <ErrorNote msg="warmup 无数据" />
          ) : (
            <>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted mb-3">
                <span>预算 {warmup.budget_s}s</span>
                <span>累计 {warmup.runs} 轮</span>
                <span>最近 {fmtTs(isRecord(warmup.last) ? warmup.last.ts : null)}</span>
              </div>
              {warmup.history.length === 0 ? (
                <div className="text-xs text-text-muted">暂无预热历史</div>
              ) : (
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {warmup.history.slice().reverse().map((h, i) => {
                    const n = isRecord(h) ? h : {};
                    const done = Object.keys(n).length;
                    return (
                      <div key={i} className="flex items-center gap-2 text-[11px]">
                        <span className="text-text-muted shrink-0">{fmtTs(n.ts)}</span>
                        <span className="text-text-secondary">预热 {done} 项路径</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </SectionCard>
      </div>

      {/* ── LLM 调用观测 ── */}
      <SectionCard
        title="LLM 调用观测"
        icon={<Activity className="h-4 w-4" />}
      >
        {!llmCalls ? (
          loading ? <Skeleton height={90} className="rounded-lg" /> : <ErrorNote msg="llm-calls 无数据" />
        ) : (
          <>
            {isRecord(llmCalls.stats) && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                {Object.entries(llmCalls.stats).slice(0, 8).map(([k, v]) => (
                  <div key={k} className="rounded-lg bg-surface-sidebar border border-subtle p-2">
                    <div className="text-[10px] text-text-muted">{k}</div>
                    <div className="text-sm font-semibold text-text-primary">{fmtVal(v)}</div>
                  </div>
                ))}
              </div>
            )}
            {llmCalls.recent.length === 0 ? (
              <div className="text-xs text-text-muted">暂无调用记录</div>
            ) : (
              <div className="space-y-1 max-h-56 overflow-y-auto">
                {llmCalls.recent.map((c, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px] py-0.5">
                    <span className="text-text-muted shrink-0">{fmtTs(c.ts)}</span>
                    <span className="font-mono text-text-secondary shrink-0">{c.stage ?? '?'}</span>
                    <span className="text-text-muted shrink-0">{c.latency_ms != null ? `${Math.round(c.latency_ms)}ms` : ''}</span>
                    {c.ok === false ? (
                      <span className="flex items-center gap-0.5 text-status-error shrink-0">
                        <AlertTriangle className="h-3 w-3" />{c.empty ? '空' : 'err'}
                      </span>
                    ) : c.empty ? (
                      <span className="text-status-warning shrink-0">空</span>
                    ) : (
                      <CheckCircle2 className="h-3 w-3 text-status-success shrink-0" />
                    )}
                    {c.trace_id && (
                      <span className="text-text-muted font-mono truncate">{String(c.trace_id).slice(0, 16)}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </SectionCard>

      {/* ── 蓝图建议 + 系统自画像 ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard
          title="蓝图自增长建议"
          icon={<Brain className="h-4 w-4" />}
        >
          {!blueprint ? (
            loading ? <Skeleton height={90} className="rounded-lg" /> : <ErrorNote msg="blueprint/suggestions 无数据" />
          ) : blueprint.suggestions.length === 0 ? (
            <div className="text-xs text-text-muted">
              {blueprint.note || '暂无建议（高频意图不足）'}
            </div>
          ) : (
            <div className="space-y-1.5">
              {blueprint.suggestions.map((s, i) => (
                <div key={i} className="rounded-lg bg-surface-sidebar border border-subtle p-2.5">
                  <div className="text-xs font-medium text-text-primary">
                    {String(s.name ?? s.intent ?? s.template ?? `建议 ${i + 1}`)}
                  </div>
                  <div className="text-[10px] text-text-muted mt-0.5">
                    {Object.entries(s).filter(([k]) => k !== 'name').map(([k, v]) =>
                      `${k}=${fmtVal(v)}`).join(' · ')}
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="系统自画像"
          icon={<FileSearch className="h-4 w-4" />}
        >
          {!profile ? (
            loading ? <Skeleton height={90} className="rounded-lg" /> : <ErrorNote msg="system-profile 无数据" />
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {Object.entries(profile).filter(([, v]) => !Array.isArray(v) && !isRecord(v)).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-text-muted shrink-0">{k}</span>
                  <span className="font-mono text-text-secondary text-right break-all">{fmtVal(v)}</span>
                </div>
              ))}
              {Array.isArray(profile.modules) && (
                <div className="rounded-lg bg-surface-sidebar border border-subtle p-2.5">
                  <div className="text-[10px] text-text-muted mb-1">模块（{profile.modules.length}）</div>
                  <div className="text-[11px] text-text-secondary break-all whitespace-pre-wrap line-clamp-6">
                    {profile.modules.slice(0, 40).map((m) => {
                      const rec = isRecord(m) ? m : { name: m };
                      return String(rec.name ?? rec.path ?? rec.module ?? JSON.stringify(m));
                    }).join(', ')}
                  </div>
                </div>
              )}
            </div>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
