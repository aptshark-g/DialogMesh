import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import type { V6GraphEditRequest } from '@/types/api';

export type GraphEditTarget =
  | { kind: 'node'; id: string; state: Record<string, unknown> }
  | { kind: 'edge'; source: string; target: string; edgeType: string; weight: number }
  | { kind: 'add_edge' };

export interface GraphEditPanelProps {
  target: GraphEditTarget | null;
  nodeIds: string[];
  submitting: boolean;
  onClose: () => void;
  onSubmit: (req: V6GraphEditRequest) => void;
}

const inputClass =
  'w-full px-3 py-2 rounded-md bg-surface border border-subtle text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-primary transition-colors';
const labelClass = 'block text-xs text-text-muted mb-1';

type EdgeAction = 'update_weight' | 'remove_edge';

export function GraphEditPanel({
  target,
  nodeIds,
  submitting,
  onClose,
  onSubmit,
}: GraphEditPanelProps) {
  const [edgeAction, setEdgeAction] = useState<EdgeAction>('update_weight');
  const [weight, setWeight] = useState('1');
  const [source, setSource] = useState('');
  const [edgeTarget, setEdgeTarget] = useState('');
  const [edgeType, setEdgeType] = useState('');
  const [stateText, setStateText] = useState('{}');
  const [jsonError, setJsonError] = useState<string | null>(null);

  // Reset form whenever the edit target changes
  useEffect(() => {
    if (!target) return;
    setJsonError(null);
    if (target.kind === 'node') {
      setStateText(JSON.stringify(target.state ?? {}, null, 2));
    } else if (target.kind === 'edge') {
      setEdgeAction('update_weight');
      setWeight(String(target.weight ?? 1));
    } else {
      setSource(nodeIds[0] ?? '');
      setEdgeTarget(nodeIds[1] ?? nodeIds[0] ?? '');
      setEdgeType('');
      setWeight('1');
    }
  }, [target, nodeIds]);

  const parsedWeight = Number(weight);

  const title =
    target?.kind === 'node'
      ? '编辑节点'
      : target?.kind === 'edge'
        ? '编辑边'
        : '添加边';

  const canSubmit = useMemo(() => {
    if (!target || submitting) return false;
    if (target.kind === 'node') return !jsonError && stateText.trim().length > 0;
    if (target.kind === 'edge') {
      return edgeAction === 'remove_edge' || Number.isFinite(parsedWeight);
    }
    return (
      source.length > 0 &&
      edgeTarget.length > 0 &&
      source !== edgeTarget &&
      Number.isFinite(parsedWeight)
    );
  }, [target, submitting, jsonError, stateText, edgeAction, parsedWeight, source, edgeTarget]);

  const handleStateChange = (value: string) => {
    setStateText(value);
    try {
      JSON.parse(value);
      setJsonError(null);
    } catch {
      setJsonError('JSON 格式错误');
    }
  };

  const handleConfirm = () => {
    if (!target) return;

    if (target.kind === 'node') {
      try {
        const parsed = JSON.parse(stateText) as Record<string, unknown>;
        onSubmit({ action: 'set_node', node_id: target.id, node_state: parsed });
      } catch {
        setJsonError('JSON 格式错误');
      }
      return;
    }

    if (target.kind === 'edge') {
      if (edgeAction === 'update_weight') {
        onSubmit({
          action: 'update_weight',
          source: target.source,
          target: target.target,
          weight: parsedWeight,
        });
      } else {
        onSubmit({ action: 'remove_edge', source: target.source, target: target.target });
      }
      return;
    }

    onSubmit({
      action: 'add_edge',
      source,
      target: edgeTarget,
      weight: parsedWeight,
      ...(edgeType.trim() ? { edge_type: edgeType.trim() } : {}),
    });
  };

  return (
    <Modal
      isOpen={target !== null}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button
            size="sm"
            onClick={handleConfirm}
            loading={submitting}
            disabled={!canSubmit}
          >
            确认
          </Button>
        </>
      }
    >
      {target?.kind === 'node' && (
        <div className="space-y-3">
          <div>
            <span className={labelClass}>节点 ID</span>
            <p className="text-sm text-text-secondary font-mono break-all">{target.id}</p>
          </div>
          <div>
            <label className={labelClass} htmlFor="graph-node-state">
              节点 State(JSON)
            </label>
            <textarea
              id="graph-node-state"
              value={stateText}
              onChange={(e) => handleStateChange(e.target.value)}
              rows={10}
              spellCheck={false}
              className={cn(inputClass, 'font-mono text-xs resize-y')}
            />
            {jsonError && <p className="text-xs text-red-500 mt-1">{jsonError}</p>}
          </div>
        </div>
      )}

      {target?.kind === 'edge' && (
        <div className="space-y-3">
          <div>
            <span className={labelClass}>边</span>
            <p className="text-sm text-text-secondary font-mono break-all">
              {target.source} → {target.target}
            </p>
            {target.edgeType && (
              <p className="text-xs text-text-muted mt-1">类型: {target.edgeType}</p>
            )}
          </div>
          <div>
            <span className={labelClass}>操作</span>
            <div className="flex items-center gap-2">
              {(
                [
                  { value: 'update_weight', label: '更新权重' },
                  { value: 'remove_edge', label: '删除边' },
                ] as { value: EdgeAction; label: string }[]
              ).map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setEdgeAction(option.value)}
                  className={cn(
                    'px-3 py-1.5 text-xs font-medium rounded-md border transition-colors',
                    edgeAction === option.value
                      ? 'bg-primary text-white border-transparent'
                      : 'border-subtle text-text-secondary hover:text-text-primary hover:bg-surface-card-hover'
                  )}
                  aria-pressed={edgeAction === option.value}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          {edgeAction === 'update_weight' ? (
            <div>
              <label className={labelClass} htmlFor="graph-edge-weight">
                权重
              </label>
              <input
                id="graph-edge-weight"
                type="number"
                step="0.1"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                className={inputClass}
              />
            </div>
          ) : (
            <div className="flex items-start gap-2 rounded-md border border-red-200 dark:border-red-900 bg-red-500/5 px-3 py-2">
              <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
              <p className="text-xs text-text-secondary">
                确认后将从图谱中删除该边,此操作立即生效。
              </p>
            </div>
          )}
        </div>
      )}

      {target?.kind === 'add_edge' && (
        <div className="space-y-3">
          <div>
            <label className={labelClass} htmlFor="graph-edge-source">
              源节点
            </label>
            <select
              id="graph-edge-source"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              className={inputClass}
            >
              {nodeIds.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="graph-edge-target">
              目标节点
            </label>
            <select
              id="graph-edge-target"
              value={edgeTarget}
              onChange={(e) => setEdgeTarget(e.target.value)}
              className={inputClass}
            >
              {nodeIds.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
            {source && edgeTarget && source === edgeTarget && (
              <p className="text-xs text-red-500 mt-1">源节点与目标节点不能相同</p>
            )}
          </div>
          <div>
            <label className={labelClass} htmlFor="graph-edge-type">
              边类型(可选)
            </label>
            <input
              id="graph-edge-type"
              type="text"
              value={edgeType}
              onChange={(e) => setEdgeType(e.target.value)}
              placeholder="如 causal / reference"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="graph-new-edge-weight">
              权重
            </label>
            <input
              id="graph-new-edge-weight"
              type="number"
              step="0.1"
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
              className={inputClass}
            />
          </div>
        </div>
      )}
    </Modal>
  );
}
