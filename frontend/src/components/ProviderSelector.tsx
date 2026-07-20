// FILE: src/components/ProviderSelector.tsx

import { useState, useEffect } from 'react';
import { ChevronDown, CheckCircle, AlertTriangle, Loader2 } from 'lucide-react';
import { getGatewayProviders, setGatewayActive } from '../api/v6';

export interface ProviderInfo {
  name: string;
  display: string;
  model: string;
  healthy: boolean;
}

interface Props {
  onSelect: (info: ProviderInfo) => void;
  active?: ProviderInfo | null;
}

export function ProviderSelector({ onSelect, active }: Props) {
  const [open, setOpen] = useState(false);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getGatewayProviders()
      .then((data: any) => {
        // Handle both raw gateway format {providers:[...]} and API proxy format
        const list = Array.isArray(data?.providers) ? data.providers
                   : Array.isArray(data) ? data
                   : data?.data?.providers || [];

        const mapped: ProviderInfo[] = [];
        for (const p of list) {
          const isConfigured = p.key_configured || p.configured;
          const isActive = p.active;
          if (!isConfigured && !isActive) continue;

          const models: any[] = Array.isArray(p.models) ? p.models : [];
          for (const m of models.slice(0, 5)) {
            const modelId = typeof m === 'string' ? m : (m.id || m.model || m.display || '');
            if (!modelId) continue;
            mapped.push({
              name: p.name,
              display: `${p.name} / ${modelId}`,
              model: modelId,
              healthy: p.healthy ? true : isActive,
            });
          }
          // If no models listed, show provider itself
          if (models.length === 0 && isConfigured) {
            mapped.push({
              name: p.name,
              display: p.name,
              model: p.default_model || '',
              healthy: isActive,
            });
          }
        }
        setProviders(mapped);
        if (mapped.length > 0 && !active) onSelect(mapped[0]);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
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
        {loading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-text-muted" />
        ) : active?.healthy ? (
          <CheckCircle className="h-3.5 w-3.5 text-status-success" />
        ) : (
          <AlertTriangle className="h-3.5 w-3.5 text-text-muted" />
        )}
        <span className="max-w-[180px] truncate">{active?.display || (loading ? '加载中...' : '选择厂商')}</span>
        <ChevronDown className="h-3.5 w-3.5 text-text-muted" />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-80 rounded-lg border border-subtle bg-surface-card shadow-card z-50">
          <div className="p-1 max-h-64 overflow-y-auto">
            {providers.length === 0 && (
              <p className="px-3 py-2 text-xs text-text-muted">
                {loading ? '加载中...' : '无可用厂商 — 请先在 Gateway 页配置 API Key'}
              </p>
            )}
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
          </div>
        </div>
      )}
    </div>
  );
}
