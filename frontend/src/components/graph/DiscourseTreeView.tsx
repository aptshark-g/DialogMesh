import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, ListTree, Pencil } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import type {
  V6DiscourseBlock,
  V6DiscourseTreeResponse,
  V6DiscourseTreeEditRequest,
} from '@/types/api';

export interface DiscourseTreeViewProps {
  data: V6DiscourseTreeResponse | null;
  loading: boolean;
  submitting: boolean;
  onEdit: (req: V6DiscourseTreeEditRequest) => Promise<boolean>;
}

type TreeEditAction = V6DiscourseTreeEditRequest['action'];

interface EditFormState {
  block: V6DiscourseBlock;
  action: TreeEditAction;
  topic: string;
  temperature: string;
  parentId: string;
}

const inputClass =
  'w-full px-3 py-2 rounded-md bg-surface border border-subtle text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-primary transition-colors';
const labelClass = 'block text-xs text-text-muted mb-1';

const ACTION_OPTIONS: { value: TreeEditAction; label: string }[] = [
  { value: 'rename', label: '重命名' },
  { value: 'reclassify', label: '重分类' },
  { value: 'merge', label: '移动/合并' },
];

interface TreeNodeProps {
  block: V6DiscourseBlock;
  childrenMap: Map<string, V6DiscourseBlock[]>;
  depth: number;
  onEditBlock: (block: V6DiscourseBlock) => void;
}

function TreeNode({ block, childrenMap, depth, onEditBlock }: TreeNodeProps) {
  const [open, setOpen] = useState(depth < 2);
  const children = childrenMap.get(block.id) ?? [];
  const hasChildren = children.length > 0;

  return (
    <div>
      <div
        className={cn(
          'group flex items-center gap-1.5 px-2 py-1.5 rounded-md',
          'hover:bg-surface-card-hover transition-colors'
        )}
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
      >
        <button
          type="button"
          onClick={() => hasChildren && setOpen((prev) => !prev)}
          className={cn(
            'p-0.5 rounded text-text-muted shrink-0',
            hasChildren ? 'hover:text-text-primary' : 'invisible'
          )}
          aria-label={open ? '折叠' : '展开'}
        >
          {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </button>
        <span className="text-sm text-text-primary truncate flex-1 min-w-0">
          {block.topic || block.id}
        </span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface border border-subtle text-text-muted shrink-0">
          {block.temperature}
        </span>
        <span className="text-[10px] text-text-muted tabular-nums shrink-0">
          EDU × {block.edus}
        </span>
        <button
          type="button"
          onClick={() => onEditBlock(block)}
          className="p-1 rounded text-text-muted hover:text-text-primary opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
          aria-label="编辑 block"
        >
          <Pencil className="w-3.5 h-3.5" />
        </button>
      </div>
      {open &&
        children.map((child) => (
          <TreeNode
            key={child.id}
            block={child}
            childrenMap={childrenMap}
            depth={depth + 1}
            onEditBlock={onEditBlock}
          />
        ))}
    </div>
  );
}

export function DiscourseTreeView({ data, loading, submitting, onEdit }: DiscourseTreeViewProps) {
  const [editForm, setEditForm] = useState<EditFormState | null>(null);

  const blocks = useMemo(() => data?.blocks ?? [], [data]);

  const { roots, childrenMap } = useMemo(() => {
    const idSet = new Set(blocks.map((b) => b.id));
    const map = new Map<string, V6DiscourseBlock[]>();
    const rootList: V6DiscourseBlock[] = [];
    for (const block of blocks) {
      if (block.parent && idSet.has(block.parent)) {
        const list = map.get(block.parent) ?? [];
        list.push(block);
        map.set(block.parent, list);
      } else {
        rootList.push(block);
      }
    }
    return { roots: rootList, childrenMap: map };
  }, [blocks]);

  const handleEditBlock = (block: V6DiscourseBlock) => {
    setEditForm({
      block,
      action: 'rename',
      topic: block.topic,
      temperature: block.temperature,
      parentId: block.parent ?? '',
    });
  };

  const canSubmit = useMemo(() => {
    if (!editForm || submitting) return false;
    if (editForm.action === 'rename') return editForm.topic.trim().length > 0;
    if (editForm.action === 'reclassify') return editForm.temperature.trim().length > 0;
    if (editForm.action === 'merge') {
      return editForm.parentId.length > 0 && editForm.parentId !== editForm.block.id;
    }
    return false;
  }, [editForm, submitting]);

  const handleConfirm = async () => {
    if (!editForm || !canSubmit) return;
    const req: V6DiscourseTreeEditRequest = {
      action: editForm.action,
      block_id: editForm.block.id,
    };
    if (editForm.action === 'rename') req.topic = editForm.topic.trim();
    else if (editForm.action === 'reclassify') req.temperature = editForm.temperature.trim();
    else if (editForm.action === 'merge') req.parent_id = editForm.parentId;

    const ok = await onEdit(req);
    if (ok) setEditForm(null);
  };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center py-16">
        <p className="text-sm text-text-muted">加载中…</p>
      </div>
    );
  }

  if (!data || blocks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <ListTree className="w-8 h-8 text-text-muted mb-3" />
        <p className="text-sm text-text-secondary">暂无对话树数据</p>
        <p className="text-xs text-text-muted mt-1">对话进行中会自动生成 discourse tree</p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-text-muted">
          共 <span className="text-text-secondary font-medium">{data.total}</span> 个 block,
          悬停节点可编辑(重命名 / 重分类 / 移动合并)
        </p>
      </div>
      <div className="rounded-xl bg-surface-card border border-subtle shadow-card p-2">
        {roots.map((block) => (
          <TreeNode
            key={block.id}
            block={block}
            childrenMap={childrenMap}
            depth={0}
            onEditBlock={handleEditBlock}
          />
        ))}
      </div>

      <Modal
        isOpen={editForm !== null}
        onClose={() => setEditForm(null)}
        title="编辑对话树 Block"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setEditForm(null)} disabled={submitting}>
              取消
            </Button>
            <Button size="sm" onClick={handleConfirm} loading={submitting} disabled={!canSubmit}>
              确认
            </Button>
          </>
        }
      >
        {editForm && (
          <div className="space-y-3">
            <div>
              <span className={labelClass}>Block ID</span>
              <p className="text-sm text-text-secondary font-mono break-all">{editForm.block.id}</p>
            </div>
            <div>
              <span className={labelClass}>操作</span>
              <div className="flex items-center gap-2 flex-wrap">
                {ACTION_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setEditForm((prev) => (prev ? { ...prev, action: option.value } : prev))}
                    className={cn(
                      'px-3 py-1.5 text-xs font-medium rounded-md border transition-colors',
                      editForm.action === option.value
                        ? 'bg-primary text-white border-transparent'
                        : 'border-subtle text-text-secondary hover:text-text-primary hover:bg-surface-card-hover'
                    )}
                    aria-pressed={editForm.action === option.value}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
            {editForm.action === 'rename' && (
              <div>
                <label className={labelClass} htmlFor="tree-edit-topic">
                  新主题
                </label>
                <input
                  id="tree-edit-topic"
                  type="text"
                  value={editForm.topic}
                  onChange={(e) => setEditForm((prev) => (prev ? { ...prev, topic: e.target.value } : prev))}
                  className={inputClass}
                />
              </div>
            )}
            {editForm.action === 'reclassify' && (
              <div>
                <label className={labelClass} htmlFor="tree-edit-temperature">
                  新 Temperature
                </label>
                <input
                  id="tree-edit-temperature"
                  type="text"
                  value={editForm.temperature}
                  onChange={(e) =>
                    setEditForm((prev) => (prev ? { ...prev, temperature: e.target.value } : prev))
                  }
                  className={inputClass}
                />
              </div>
            )}
            {editForm.action === 'merge' && (
              <div>
                <label className={labelClass} htmlFor="tree-edit-parent">
                  新父节点
                </label>
                <select
                  id="tree-edit-parent"
                  value={editForm.parentId}
                  onChange={(e) => setEditForm((prev) => (prev ? { ...prev, parentId: e.target.value } : prev))}
                  className={inputClass}
                >
                  <option value="">选择父节点…</option>
                  {blocks
                    .filter((b) => b.id !== editForm.block.id)
                    .map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.topic || b.id}
                      </option>
                    ))}
                </select>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
