// FILE: src/components/ProviderSelector.tsx
// 对话页顶部的 LLM 厂商选择器

import { useState, useEffect } from 'react';
import { ChevronDown, CheckCircle, AlertTriangle } from 'lucide-react';
import { getGatewayProviders, setGatewayActive } from '../api/v6';

export interface ProviderInfo {
  name: string;
  display: string;
  model: string;
  healthy: boolean;
  latency?: number;
}

interface Props {
  onSelect: (info: ProviderInfo) => void;
  active?: ProviderInfo | null;
}

export function ProviderSelector({ onSelect, active }: Props) {
  const [open, setOpen] = useState(false);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);

  useEffect(() => {
    getGatewayProviders()
      .then(data => {
        const list = (data as any).providers || data || [];
        const mapped: ProviderInfo[] = [];
        for (const p of list) {
          if (!p.active && !p.configured) continue;
          for (const m of (p.models || []).slice(0, 3)) {
            const modelId = typeof m === 'string' ? m : m.id || m.display || m;
            mapped.push({
              name: p.name,
              display: `${p.name} / ${modelId}`,
              model: modelId,
              healthy: p.healthy ?? false,
            });
          }
        }
        setProviders(mapped);
        if (mapped.length > 0 && !active) onSelect(mapped[0]);
      })
      .catch(() => {});
  }, []);

  const handleSelect = async (p: ProviderInfo) => {
    try {
      await setGatewayActive({ provider: p.name, model: p.model });
    } catch {}
    onSelect(p);
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-card border border-subtle text-sm text-text-primary hover:border-primary/30 transition-colors"
      >
        <span className={active?.healthy ? 'text-status-success' : 'text-status-error'}>
          {active?.healthy ? <CheckCircle className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />}
        </span>
        <span className="max-w-[160px] truncate">{active?.display || '选择厂商'}</span>
        <ChevronDown className="h-3.5 w-3.5 text-text-muted" />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-72 rounded-lg border border-subtle bg-surface-card shadow-card z-50">
          <div className="p-1">
            {providers.map(p => (
              <button
                key={p.display}
                onClick={() => handleSelect(p)}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-left hover:bg-surface-sidebar transition-colors"
              >
                <span className={p.healthy ? 'text-status-success' : 'text-text-muted'}>
                  {p.healthy ? <CheckCircle className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
                </span>
                <span className="flex-1 truncate">{p.display}</span>
              </button>
            ))}
            {providers.length === 0 && (
              <p className="px-3 py-2 text-xs text-text-muted">无可用厂商 (请先在 Gateway 页配置 API Key)</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
