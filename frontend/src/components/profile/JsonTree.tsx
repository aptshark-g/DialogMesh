// FILE: src/components/profile/JsonTree.tsx
// 通用 unknown 结构层级渲染(用于 Mind 空间 / ABC 等 Record<string, unknown> 数据)

import type { FC } from 'react';

const MAX_DEPTH = 6;
const MAX_ITEMS = 50;

function isComposite(v: unknown): v is Record<string, unknown> | unknown[] {
  return v !== null && typeof v === 'object';
}

function formatPrimitive(v: unknown): string {
  if (v === null) return 'null';
  if (v === undefined) return 'undefined';
  if (typeof v === 'string') return v === '' ? '(空字符串)' : v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

export function previewValue(v: unknown, maxLength: number = 80): string {
  const s = isComposite(v) ? safeStringify(v) : formatPrimitive(v);
  return s.length > maxLength ? `${s.slice(0, maxLength)}…` : s;
}

function safeStringify(v: unknown): string {
  try {
    return JSON.stringify(v) ?? String(v);
  } catch {
    return String(v);
  }
}

interface JsonTreeProps {
  value: unknown;
  depth?: number;
}

export const JsonTree: FC<JsonTreeProps> = ({ value, depth = 0 }) => {
  if (value === null || value === undefined) {
    return <span className="text-text-muted italic">null</span>;
  }

  if (typeof value !== 'object') {
    return (
      <span className="text-xs text-text-secondary break-all">
        {formatPrimitive(value)}
      </span>
    );
  }

  if (depth >= MAX_DEPTH) {
    return (
      <span className="text-xs text-text-muted break-all">{previewValue(value, 120)}</span>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-xs text-text-muted">[ ]（空数组）</span>;
    }
    return (
      <div className="space-y-1.5">
        {value.slice(0, MAX_ITEMS).map((item, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-xs text-text-muted shrink-0 w-6 text-right tabular-nums">
              {i}
            </span>
            <div className="min-w-0 flex-1 border-l border-border-subtle pl-2">
              <JsonTree value={item} depth={depth + 1} />
            </div>
          </div>
        ))}
        {value.length > MAX_ITEMS && (
          <p className="text-xs text-text-muted">… 共 {value.length} 项,仅显示前 {MAX_ITEMS} 项</p>
        )}
      </div>
    );
  }

  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) {
    return <span className="text-xs text-text-muted">{'{ }'}（空对象）</span>;
  }
  return (
    <div className="space-y-1.5">
      {entries.slice(0, MAX_ITEMS).map(([k, v]) =>
        isComposite(v) ? (
          <div key={k}>
            <span className="text-xs font-semibold text-text-primary">{k}</span>
            <div className="mt-1 border-l border-border-subtle pl-3">
              <JsonTree value={v} depth={depth + 1} />
            </div>
          </div>
        ) : (
          <div key={k} className="flex items-baseline gap-2">
            <span className="text-xs font-medium text-text-muted shrink-0">{k}</span>
            <span className="text-xs text-text-secondary break-all">{formatPrimitive(v)}</span>
          </div>
        )
      )}
      {entries.length > MAX_ITEMS && (
        <p className="text-xs text-text-muted">
          … 共 {entries.length} 个字段,仅显示前 {MAX_ITEMS} 个
        </p>
      )}
    </div>
  );
};

export default JsonTree;
