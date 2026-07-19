// FILE: frontend/src/components/sessions/PersistenceOverview.tsx
// 持久化状态卡 — 存储后端概览 + 图数据清单

import {
  Brain,
  Database,
  GitFork,
  Layers,
  ShieldCheck,
} from 'lucide-react';
import type {
  V6PersistenceGraphsResponse,
  V6PersistenceResponse,
} from '../../types/api';
import { cn } from '../../lib/utils';
import { Skeleton } from '../ui/Skeleton';

interface PersistenceOverviewProps {
  persistence: V6PersistenceResponse | null;
  graphs: V6PersistenceGraphsResponse | null;
  loading: boolean;
  graphsLoading: boolean;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** 从 store stats 中提取前几个标量字段展示 */
function storeMetrics(store: unknown): [string, string][] {
  if (!isRecord(store)) return [];
  return Object.entries(store)
    .filter(([, v]) => ['string', 'number', 'boolean'].includes(typeof v))
    .slice(0, 3)
    .map(([k, v]) => [k, String(v)]);
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString('zh-CN', { hour12: false });
}

interface TileProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  ok: boolean | null;
  metrics?: [string, string][];
}

function Tile({ icon, label, value, ok, metrics }: TileProps) {
  return (
    <div className="bg-surface-card rounded-xl border border-subtle p-4 shadow-card">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-text-muted">
          {icon}
          <span className="text-xs font-medium">{label}</span>
        </div>
        {ok !== null && (
          <span
            className={cn(
              'h-2 w-2 rounded-full',
              ok ? 'bg-status-success' : 'bg-status-pending'
            )}
          />
        )}
      </div>
      <p
        className={cn(
          'text-base font-semibold',
          ok === false ? 'text-text-muted' : 'text-text-primary'
        )}
      >
        {value}
      </p>
      {metrics && metrics.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {metrics.map(([k, v]) => (
            <span
              key={k}
              className="px-1.5 py-0.5 rounded bg-surface-card-hover text-[11px] text-text-secondary font-mono"
            >
              {k}: {v}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function PersistenceOverview({
  persistence,
  graphs,
  loading,
  graphsLoading,
}: PersistenceOverviewProps) {
  if (loading && !persistence) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} height={86} className="rounded-xl" />
        ))}
      </div>
    );
  }

  const annotationOn = persistence?.annotation_store != null;
  const unifiedOn = persistence?.unified_store != null;
  const graphList = graphs?.graphs ?? [];
  const totalNodes = graphList.reduce((s, g) => s + g.node_count, 0);
  const totalEdges = graphList.reduce((s, g) => s + g.edge_count, 0);

  return (
    <div className="mb-6">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Tile
          icon={<Database className="h-3.5 w-3.5" />}
          label="Annotation Store"
          value={annotationOn ? '运行中' : '未启用'}
          ok={annotationOn}
          metrics={storeMetrics(persistence?.annotation_store)}
        />
        <Tile
          icon={<Layers className="h-3.5 w-3.5" />}
          label="Unified Store"
          value={unifiedOn ? '运行中' : '未启用'}
          ok={unifiedOn}
          metrics={storeMetrics(persistence?.unified_store)}
        />
        <Tile
          icon={<Brain className="h-3.5 w-3.5" />}
          label="OCEAN 画像"
          value={persistence?.oceAN_saved ? '已保存' : '未保存'}
          ok={persistence?.oceAN_saved ?? null}
        />
        <Tile
          icon={<ShieldCheck className="h-3.5 w-3.5" />}
          label="规则库"
          value={persistence?.rules_saved ? '已保存' : '未保存'}
          ok={persistence?.rules_saved ?? null}
        />
        <Tile
          icon={<GitFork className="h-3.5 w-3.5" />}
          label="图数据"
          value={graphsLoading ? '加载中…' : `${graphList.length} 个图`}
          ok={graphList.length > 0 ? true : graphs ? false : null}
          metrics={
            graphList.length > 0
              ? [
                  ['节点', String(totalNodes)],
                  ['边', String(totalEdges)],
                ]
              : undefined
          }
        />
      </div>

      {graphList.length > 0 && (
        <div className="mt-3 bg-surface-card rounded-xl border border-subtle shadow-card divide-y divide-border-subtle">
          {graphList.map((g) => (
            <div
              key={g.name}
              className="flex items-center gap-3 px-4 py-2.5 text-xs"
            >
              <GitFork className="h-3.5 w-3.5 text-primary shrink-0" />
              <span className="font-medium text-text-primary truncate">
                {g.name}
              </span>
              <span className="text-text-muted shrink-0">
                {g.node_count} 节点 · {g.edge_count} 边
              </span>
              <span className="ml-auto text-text-muted shrink-0">
                更新于 {formatTime(g.updated_at)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
