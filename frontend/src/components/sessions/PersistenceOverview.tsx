// FILE: frontend/src/components/sessions/PersistenceOverview.tsx
// 持久化状态卡 — 存储后端概览 + 图数据清单
// 2026-08-17: 改为用户可读的五格状态（中文标签 + 一句用途说明）,
// 不再直接展示 status/records 这类内部字段。

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

interface TileProps {
  icon: React.ReactNode;
  label: string;
  hint: string;
  value: string;
  ok: boolean | null;
  sub?: string;
}

function Tile({ icon, label, hint, value, ok, sub }: TileProps) {
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
      <p className="text-[11px] text-text-muted leading-snug mb-2">{hint}</p>
      <p
        className={cn(
          'text-base font-semibold',
          ok === false ? 'text-text-muted' : 'text-text-primary'
        )}
      >
        {value}
      </p>
      {sub && <p className="text-xs text-text-secondary mt-1">{sub}</p>}
    </div>
  );
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString('zh-CN', { hour12: false });
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
          label="记忆批注"
          hint="对话与反馈的结构化批注存储"
          value={annotationOn ? '运行中' : '未启用'}
          ok={annotationOn}
        />
        <Tile
          icon={<Layers className="h-3.5 w-3.5" />}
          label="统一记忆"
          hint="多树记忆的统一落盘层"
          value={unifiedOn ? '运行中' : '未启用'}
          ok={unifiedOn}
        />
        <Tile
          icon={<Brain className="h-3.5 w-3.5" />}
          label="用户画像"
          hint="OCEAN 五维人格画像"
          value={persistence?.oceAN_saved ? '已保存' : '未保存'}
          ok={persistence?.oceAN_saved ?? null}
        />
        <Tile
          icon={<ShieldCheck className="h-3.5 w-3.5" />}
          label="规则库"
          hint="用户约束规则（可编辑）"
          value={persistence?.rules_saved ? '已保存' : '未保存'}
          ok={persistence?.rules_saved ?? null}
        />
        <Tile
          icon={<GitFork className="h-3.5 w-3.5" />}
          label="知识图谱"
          hint="记忆与知识的图谱表示"
          value={graphsLoading ? '加载中…' : `${graphList.length} 个图`}
          ok={graphList.length > 0 ? true : graphs ? false : null}
          sub={graphList.length > 0 ? `${totalNodes} 节点 · ${totalEdges} 边` : undefined}
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
