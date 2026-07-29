import { useMemo, useState } from 'react';
import { Boxes, Pencil } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import type {
  V6ObjectNode,
  V6ObjectsResponse,
  V6ObjectEditRequest,
} from '@/types/api';

export interface ObjectsViewProps {
  data: V6ObjectsResponse | null;
  loading: boolean;
  submitting: boolean;
  onEdit: (req: V6ObjectEditRequest) => Promise<boolean>;
}

type ObjectEditAction = V6ObjectEditRequest['action'];

interface EditFormState {
  object: V6ObjectNode;
  action: ObjectEditAction;
  newName: string;
  lifespan: string;
  target: string;
  relationType: string;
}

const inputClass =
  'w-full px-3 py-2 rounded-md bg-surface border border-subtle text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-primary transition-colors';
const labelClass = 'block text-xs text-text-muted mb-1';

const ACTION_OPTIONS: { value: ObjectEditAction; label: string }[] = [
  { value: 'rename', label: '重命名' },
  { value: 'set_lifespan', label: '设置 Lifespan' },
  { value: 'relate', label: '添加关系' },
  { value: 'unrelate', label: '移除关系' },
];

export function ObjectsView({ data, loading, submitting, onEdit }: ObjectsViewProps) {
  const [editForm, setEditForm] = useState<EditFormState | null>(null);

  const objects = useMemo(() => data?.nodes ?? [], [data]);
  const objectIds = useMemo(() => objects.map((o) => o.id), [objects]);

  const handleEditObject = (object: V6ObjectNode) => {
    setEditForm({
      object,
      action: 'rename',
      newName: object.id,
      lifespan: object.lifespan,
      target: '',
      relationType: '',
    });
  };

  const canSubmit = useMemo(() => {
    if (!editForm || submitting) return false;
    switch (editForm.action) {
      case 'rename':
        return editForm.newName.trim().length > 0;
      case 'set_lifespan':
        return editForm.lifespan.trim().length > 0;
      case 'relate':
        return (
          editForm.target.length > 0 &&
          editForm.target !== editForm.object.id &&
          editForm.relationType.trim().length > 0
        );
      case 'unrelate':
        return editForm.target.length > 0;
      default:
        return false;
    }
  }, [editForm, submitting]);

  const handleConfirm = async () => {
    if (!editForm || !canSubmit) return;
    const req: V6ObjectEditRequest = { action: editForm.action };
    if (editForm.action === 'rename') {
      req.source = editForm.object.id;
      req.new_name = editForm.newName.trim();
    } else if (editForm.action === 'set_lifespan') {
      req.source = editForm.object.id;
      req.lifespan = editForm.lifespan.trim();
    } else if (editForm.action === 'relate') {
      req.source = editForm.object.id;
      req.target = editForm.target;
      req.relation_type = editForm.relationType.trim();
    } else if (editForm.action === 'unrelate') {
      req.source = editForm.object.id;
      req.target = editForm.target;
    }

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

  if (!data || objects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <Boxes className="w-8 h-8 text-text-muted mb-3" />
        <p className="text-sm text-text-secondary">暂无语义对象</p>
        <p className="text-xs text-text-muted mt-1">对话中提取的语义对象会显示在这里</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-text-muted">
          共 <span className="text-text-secondary font-medium">{data.total_objects}</span> 个语义对象
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {objects.map((object) => (
          <div
            key={object.id}
            className="group rounded-xl bg-surface-card border border-subtle shadow-card p-3 hover:shadow-card-hover transition-shadow"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-sm font-medium text-text-primary font-mono break-all min-w-0">
                {object.id}
              </span>
              <button
                type="button"
                onClick={() => handleEditObject(object)}
                className="p-1 rounded text-text-muted hover:text-text-primary opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                aria-label="编辑对象"
              >
                <Pencil className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface border border-subtle text-text-muted">
                lifespan: {object.lifespan}
              </span>
            </div>
            {object.relations?.length > 0 && (
              <div className="mt-2">
                <span className="text-[10px] text-text-muted">关系</span>
                <div className="mt-1 flex items-center gap-1 flex-wrap">
                  {object.relations.map((rel) => (
                    <span
                      key={rel}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-mono"
                    >
                      {rel}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <Modal
        isOpen={editForm !== null}
        onClose={() => setEditForm(null)}
        title="编辑语义对象"
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
              <span className={labelClass}>对象 ID</span>
              <p className="text-sm text-text-secondary font-mono break-all">{editForm.object.id}</p>
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
                <label className={labelClass} htmlFor="object-edit-name">
                  新名称
                </label>
                <input
                  id="object-edit-name"
                  type="text"
                  value={editForm.newName}
                  onChange={(e) => setEditForm((prev) => (prev ? { ...prev, newName: e.target.value } : prev))}
                  className={inputClass}
                />
              </div>
            )}
            {editForm.action === 'set_lifespan' && (
              <div>
                <label className={labelClass} htmlFor="object-edit-lifespan">
                  Lifespan
                </label>
                <input
                  id="object-edit-lifespan"
                  type="text"
                  value={editForm.lifespan}
                  onChange={(e) => setEditForm((prev) => (prev ? { ...prev, lifespan: e.target.value } : prev))}
                  placeholder="如 session / persistent"
                  className={inputClass}
                />
              </div>
            )}
            {editForm.action === 'relate' && (
              <>
                <div>
                  <label className={labelClass} htmlFor="object-edit-target">
                    目标对象
                  </label>
                  <select
                    id="object-edit-target"
                    value={editForm.target}
                    onChange={(e) => setEditForm((prev) => (prev ? { ...prev, target: e.target.value } : prev))}
                    className={inputClass}
                  >
                    <option value="">选择目标对象…</option>
                    {objectIds
                      .filter((id) => id !== editForm.object.id)
                      .map((id) => (
                        <option key={id} value={id}>
                          {id}
                        </option>
                      ))}
                  </select>
                </div>
                <div>
                  <label className={labelClass} htmlFor="object-edit-relation-type">
                    关系类型
                  </label>
                  <input
                    id="object-edit-relation-type"
                    type="text"
                    value={editForm.relationType}
                    onChange={(e) =>
                      setEditForm((prev) => (prev ? { ...prev, relationType: e.target.value } : prev))
                    }
                    placeholder="如 related_to / part_of"
                    className={inputClass}
                  />
                </div>
              </>
            )}
            {editForm.action === 'unrelate' && (
              <div>
                <label className={labelClass} htmlFor="object-edit-unrelate-target">
                  要移除的关系
                </label>
                {editForm.object.relations?.length > 0 ? (
                  <select
                    id="object-edit-unrelate-target"
                    value={editForm.target}
                    onChange={(e) => setEditForm((prev) => (prev ? { ...prev, target: e.target.value } : prev))}
                    className={inputClass}
                  >
                    <option value="">选择目标对象…</option>
                    {editForm.object.relations.map((rel) => (
                      <option key={rel} value={rel}>
                        {rel}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="text-xs text-text-muted">该对象暂无关系可移除</p>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
