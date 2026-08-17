// FILE: src/components/ProviderSelector.tsx

import { useState, useEffect } from 'react';
import { ChevronDown, CheckCircle, AlertTriangle, Loader2 } from 'lucide-react';
import { getGatewayProviders, setGatewayActive } from '../api/v6';
import { specMove } from '@/lib/spec';

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
        onPointerMove={specMove}
        className="spec-item relative flex items-center gap-2 px-3 py-1.5 rounded-full border border-hairline shadow-card text-sm text-text-primary bg-glass/60 backdrop-blur-xl transition-colors"
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
        <div onPointerMove={specMove}
          className="spec-panel absolute top-full left-0 mt-1 w-80 rounded-xl glass-panel z-50 overflow-hidden">
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
                onPointerMove={specMove}
                className="spec-item w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left text-text-primary transition-colors hover:bg-wash"
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
