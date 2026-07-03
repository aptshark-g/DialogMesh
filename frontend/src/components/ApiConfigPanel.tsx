import { useState, useEffect, useCallback } from 'react';
import { Server, RotateCcw, Check, AlertCircle, ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { getApiConfig, setApiConfig, resetApiConfig } from '../lib/config';

const PROVIDERS = [
  { id: 'custom', label: '自定义', restUrl: '', wsUrl: '' },
  { id: 'lmstudio', label: 'LM Studio', restUrl: 'http://localhost:1234', wsUrl: 'ws://localhost:1234' },
  { id: 'ollama', label: 'Ollama', restUrl: 'http://localhost:11434', wsUrl: 'ws://localhost:11434' },
  { id: 'openai', label: 'OpenAI', restUrl: 'https://api.openai.com', wsUrl: 'wss://api.openai.com' },
] as const;

type ProviderId = (typeof PROVIDERS)[number]['id'];

export interface ApiConfigPanelProps {
  /** 保存成功回调 */
  onSave?: () => void;
}

export function ApiConfigPanel({ onSave }: ApiConfigPanelProps) {
  const [provider, setProvider] = useState<ProviderId>('custom');
  const [restUrl, setRestUrl] = useState('');
  const [wsUrl, setWsUrl] = useState('');
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [providerOpen, setProviderOpen] = useState(false);

  // Load current config on mount
  useEffect(() => {
    const cfg = getApiConfig();
    setRestUrl(cfg.restBaseUrl);
    setWsUrl(cfg.wsBaseUrl);
  }, []);

  const handleProviderChange = useCallback((pid: ProviderId) => {
    setProvider(pid);
    setProviderOpen(false);
    const p = PROVIDERS.find((x) => x.id === pid);
    if (p && p.restUrl) {
      setRestUrl(p.restUrl);
      setWsUrl(p.wsUrl);
    }
  }, []);

  const validateUrl = (url: string, protocol: string): string | null => {
    if (!url.trim()) return 'URL 不能为空';
    if (!url.startsWith(protocol)) return `URL 必须以 ${protocol}:// 开头`;
    try {
      new URL(url);
      return null;
    } catch {
      return '无效的 URL 格式';
    }
  };

  const handleSave = useCallback(() => {
    setError(null);
    setSaved(false);

    const restError = validateUrl(restUrl, 'http');
    if (restError) {
      setError(`REST API: ${restError}`);
      return;
    }

    const wsError = validateUrl(wsUrl, 'ws');
    if (wsError) {
      setError(`WebSocket: ${wsError}`);
      return;
    }

    setApiConfig({
      restBaseUrl: restUrl.trim().replace(/\/$/, ''),
      wsBaseUrl: wsUrl.trim().replace(/\/$/, ''),
    });

    setSaved(true);
    onSave?.();

    // Auto-hide saved indicator
    setTimeout(() => setSaved(false), 2000);
  }, [restUrl, wsUrl, onSave]);

  const handleReset = useCallback(() => {
    resetApiConfig();
    const cfg = getApiConfig();
    setRestUrl(cfg.restBaseUrl);
    setWsUrl(cfg.wsBaseUrl);
    setProvider('custom');
    setSaved(false);
    setError(null);
  }, []);

  const inputClass = [
    'w-full px-4 py-2 rounded-lg border',
    'bg-surface-main text-text-primary text-sm',
    'focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary',
    'border-gray-200 dark:border-gray-700',
  ].join(' ');

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.1 }}
      className="bg-surface-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6"
    >
      <div className="flex items-center gap-3 mb-4">
        <Server className="w-5 h-5 text-primary" />
        <h2 className="text-base font-semibold text-text-primary">后端连接</h2>
      </div>

      <div className="space-y-4">
        {/* Provider Selector */}
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">
            API Provider
          </label>
          <div className="relative">
            <button
              type="button"
              onClick={() => setProviderOpen((v) => !v)}
              className={[
                inputClass,
                'flex items-center justify-between text-left',
              ].join(' ')}
            >
              <span>
                {PROVIDERS.find((p) => p.id === provider)?.label || '自定义'}
              </span>
              <ChevronDown className={`w-4 h-4 text-text-muted transition-transform ${providerOpen ? 'rotate-180' : ''}`} />
            </button>
            <AnimatePresence>
              {providerOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.15 }}
                  className="absolute z-20 mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-surface-card shadow-card overflow-hidden"
                >
                  {PROVIDERS.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => handleProviderChange(p.id)}
                      className={[
                        'w-full px-4 py-2 text-left text-sm transition-colors',
                        'hover:bg-surface-card-hover',
                        provider === p.id ? 'text-primary bg-primary/5' : 'text-text-secondary',
                      ].join(' ')}
                    >
                      {p.label}
                      {p.restUrl && (
                        <span className="block text-[10px] text-text-muted mt-0.5">
                          {p.restUrl}
                        </span>
                      )}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* REST URL */}
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">
            REST API Base URL
          </label>
          <input
            type="text"
            value={restUrl}
            onChange={(e) => setRestUrl(e.target.value)}
            placeholder="http://localhost:8000"
            className={inputClass}
          />
          <p className="mt-1 text-xs text-text-muted">
            后端 REST API 的根地址，用于会话管理和消息发送
          </p>
        </div>

        {/* WebSocket URL */}
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">
            WebSocket Base URL
          </label>
          <input
            type="text"
            value={wsUrl}
            onChange={(e) => setWsUrl(e.target.value)}
            placeholder="ws://localhost:8000"
            className={inputClass}
          />
          <p className="mt-1 text-xs text-text-muted">
            WebSocket 连接根地址，用于实时消息推送
          </p>
        </div>

        {/* Feedback */}
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="flex items-center gap-2 text-sm text-status-error"
          >
            <AlertCircle className="w-4 h-4" />
            {error}
          </motion.div>
        )}

        {saved && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="flex items-center gap-2 text-sm text-status-success"
          >
            <Check className="w-4 h-4" />
            配置已保存
          </motion.div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 pt-2">
          <button
            type="button"
            onClick={handleSave}
            className={[
              'px-4 py-2 rounded-lg text-sm font-medium',
              'bg-primary text-white hover:bg-primary-dark',
              'transition-colors focus:outline-none focus:ring-2 focus:ring-primary/30',
            ].join(' ')}
          >
            保存配置
          </button>

          <button
            type="button"
            onClick={handleReset}
            className={[
              'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm',
              'border border-gray-200 dark:border-gray-700 text-text-secondary',
              'hover:bg-surface-card-hover transition-colors',
            ].join(' ')}
          >
            <RotateCcw className="w-3.5 h-3.5" />
            恢复默认
          </button>
        </div>
      </div>
    </motion.div>
  );
}
