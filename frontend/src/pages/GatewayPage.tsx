// FILE: src/pages/GatewayPage.tsx
// Gateway — 服务检测 + Provider 管理 + 配置 + 用量 + 运维

import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Shield,
  Server,
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Play,
  Settings,
  KeyRound,
  Globe,
  Zap,
  Activity,
  Coins,
  BarChart3,
  ChevronDown,
  ChevronUp,
  Loader2,
  RotateCcw,
  Layers,
  // Clock,  // unused
  ArrowRight,
} from 'lucide-react';
import { useV6Gateway } from '../hooks/useV6Gateway';
import { cn } from '../lib/utils';
import type { V6GatewayProvider, V6GatewayModel } from '../types/api';

export function GatewayPage() {
  const {
    dmStatus, swStatus, statusLoading,
    gatewayProviders, providersLoading,
    router,
    tokens,
    metrics,
    config, configLoading,
    usage, usageLoading,
    stats, statsLoading,
    health, healthLoading,
    error, saveLoading, testLoading, fetchModelsLoading,
    refresh,
    checkServices,
    configProvider,
    testProvider,
    fetchProviderModels,
    setActive,
    reload,
  } = useV6Gateway(true, 15000);

  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  const [configForms, setConfigForms] = useState<Record<string, { apiKey: string; baseUrl: string }>>({});
  const [testResults, setTestResults] = useState<Record<string, { healthy: boolean; latency: number; error: string | null }>>({});
  const [activeTab, setActiveTab] = useState<'providers' | 'usage' | 'config' | 'monitor'>('providers');

  const toggleExpand = (name: string) => {
    setExpandedProvider(prev => prev === name ? null : name);
  };

  const updateConfigForm = (name: string, field: 'apiKey' | 'baseUrl', value: string) => {
    setConfigForms(prev => ({
      ...prev,
      [name]: { ...(prev[name] || { apiKey: '', baseUrl: '' }), [field]: value },
    }));
  };

  const handleTest = useCallback(async (name: string) => {
    const result = await testProvider(name);
    if (result) {
      setTestResults(prev => ({
        ...prev,
        [name]: { healthy: result.healthy, latency: result.latency_ms, error: result.error },
      }));
    }
  }, [testProvider]);

  const handleSaveConfig = useCallback(async (name: string) => {
    const form = configForms[name];
    if (!form) return;
    await configProvider(name, { api_key: form.apiKey, base_url: form.baseUrl });
  }, [configForms, configProvider]);

  const handleSetActive = useCallback(async (provider: string, model: string) => {
    await setActive({ provider, model });
  }, [setActive]);

  const handleFetchModels = useCallback(async (name: string) => {
    await fetchProviderModels(name);
  }, [fetchProviderModels]);

  const fadeIn = (delay: number) => ({
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, delay },
  });

  // ─── Service Status Card ───
  const StatusCard = ({ title, status, icon: Icon, port }: {
    title: string; status: typeof dmStatus; icon: typeof Server; port: string;
  }) => {
    const isHealthy = status?.healthy ?? false;
    const isLoading = statusLoading;
    return (
      <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-text-muted" />
            <span className="text-sm font-semibold text-text-primary">{title}</span>
          </div>
          <span className="text-xs text-text-muted">{port}</span>
        </div>
        <div className="flex items-center gap-3">
          {isLoading ? (
            <Loader2 className="h-5 w-5 animate-spin text-text-muted" />
          ) : isHealthy ? (
            <CheckCircle className="h-5 w-5 text-status-success" />
          ) : (
            <XCircle className="h-5 w-5 text-status-error" />
          )}
          <div>
            <div className={cn(
              'text-sm font-medium',
              isLoading ? 'text-text-muted' : isHealthy ? 'text-status-success' : 'text-status-error'
            )}>
              {isLoading ? '检测中...' : isHealthy ? '运行中' : '未连接'}
            </div>
            {status?.latency_ms !== null && status?.latency_ms !== undefined && (
              <div className="text-xs text-text-muted">{status.latency_ms}ms</div>
            )}
            {status?.error && (
              <div className="text-xs text-status-error mt-1">{status.error}</div>
            )}
          </div>
        </div>
        {status?.version && (
          <div className="mt-2 text-xs text-text-muted">版本: {status.version}</div>
        )}
      </div>
    );
  };

  // ─── Provider Card ───
  const ProviderCard = ({ provider }: { provider: V6GatewayProvider }) => {
    const isExpanded = expandedProvider === provider.name;
    const isActive = gatewayProviders?.active_provider === provider.name;
    const testResult = testResults[provider.name];
    const isTesting = testLoading === provider.name;
    const isFetchingModels = fetchModelsLoading === provider.name;
    const form = configForms[provider.name] || { apiKey: '', baseUrl: provider.base_url || '' };

    return (
      <div className={cn(
        'bg-surface-card rounded-xl border transition-colors',
        isActive ? 'border-primary ring-1 ring-primary/20' : 'border-gray-200'
      )}>
        <button
          onClick={() => toggleExpand(provider.name)}
          className="w-full flex items-center justify-between p-4 text-left"
        >
          <div className="flex items-center gap-3">
            <div className={cn(
              'h-8 w-8 rounded-lg flex items-center justify-center',
              provider.configured ? 'bg-primary/10' : 'bg-gray-100',
              isActive && 'ring-2 ring-primary/30'
            )}>
              {provider.configured ? (
                <CheckCircle className="h-4 w-4 text-primary" />
              ) : (
                <AlertTriangle className="h-4 w-4 text-text-muted" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-text-primary">{provider.display_name}</span>
                {isActive && (
                  <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-primary/10 text-primary">当前</span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className={cn(
                  'text-xs',
                  provider.healthy === true ? 'text-status-success' :
                  provider.healthy === false ? 'text-status-error' : 'text-text-muted'
                )}>
                  {provider.healthy === true ? '● 健康' :
                   provider.healthy === false ? '● 异常' : '● 未配置'}
                </span>
                <span className="text-xs text-text-muted">{provider.base_url}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isActive && gatewayProviders?.active_model && (
              <span className="text-xs text-text-muted font-mono">{gatewayProviders.active_model}</span>
            )}
            {isExpanded ? <ChevronUp className="h-4 w-4 text-text-muted" /> : <ChevronDown className="h-4 w-4 text-text-muted" />}
          </div>
        </button>

        <AnimatePresence>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-4 space-y-4">
                {/* Config Form */}
                <div className="rounded-lg border border-gray-100 p-3 space-y-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-text-muted">
                    <KeyRound className="h-3.5 w-3.5" />
                    配置
                  </div>
                  <div className="space-y-2">
                    <div>
                      <label className="text-xs text-text-muted">API Key</label>
                      <input
                        type="password"
                        value={form.apiKey}
                        onChange={(e) => updateConfigForm(provider.name, 'apiKey', e.target.value)}
                        placeholder={provider.api_key ? '●●●●●●●● (已配置)' : '输入 API Key'}
                        className="w-full mt-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-text-muted">Base URL</label>
                      <input
                        type="text"
                        value={form.baseUrl}
                        onChange={(e) => updateConfigForm(provider.name, 'baseUrl', e.target.value)}
                        placeholder="https://api.example.com/v1"
                        className="w-full mt-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleSaveConfig(provider.name)}
                      disabled={saveLoading}
                      className="flex items-center gap-1 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
                    >
                      <Settings className="h-3.5 w-3.5" />
                      {saveLoading ? '保存中...' : '保存'}
                    </button>
                    <button
                      onClick={() => handleTest(provider.name)}
                      disabled={isTesting}
                      className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
                    >
                      {isTesting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
                      {isTesting ? '测试中...' : '测试连接'}
                    </button>
                    <button
                      onClick={() => handleFetchModels(provider.name)}
                      disabled={isFetchingModels}
                      className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
                    >
                      {isFetchingModels ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Globe className="h-3.5 w-3.5" />}
                      {isFetchingModels ? '拉取中...' : '拉取模型'}
                    </button>
                  </div>
                  {testResult && (
                    <div className={cn(
                      'rounded-lg px-3 py-2 text-xs',
                      testResult.healthy ? 'bg-status-success/10 text-status-success' : 'bg-status-error/10 text-status-error'
                    )}>
                      {testResult.healthy ? (
                        <span>✅ 连接成功 · {testResult.latency}ms</span>
                      ) : (
                        <span>❌ 连接失败{testResult.error ? `: ${testResult.error}` : ''}</span>
                      )}
                    </div>
                  )}
                </div>

                {/* Models */}
                {provider.models && provider.models.length > 0 && (
                  <div className="rounded-lg border border-gray-100 p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-text-muted mb-2">
                      <Layers className="h-3.5 w-3.5" />
                      可用模型 ({provider.models.length})
                    </div>
                    <div className="space-y-1">
                      {provider.models.map((model: V6GatewayModel) => {
                        const isModelActive = isActive && gatewayProviders?.active_model === model.id;
                        return (
                          <div
                            key={model.id}
                            className={cn(
                              'flex items-center justify-between rounded-lg px-3 py-2 transition-colors',
                              isModelActive ? 'bg-primary/5 border border-primary/20' : 'hover:bg-gray-50'
                            )}
                          >
                            <div className="flex items-center gap-2">
                              <span className="text-sm text-text-primary font-mono">{model.id}</span>
                              <span className="text-xs text-text-muted">{model.display}</span>
                            </div>
                            <div className="flex items-center gap-3">
                              <span className="text-xs text-text-muted">{model.context.toLocaleString()} ctx</span>
                              <span className="text-xs text-text-muted">${model.cost_in}/M</span>
                              <button
                                onClick={() => handleSetActive(provider.name, model.id)}
                                disabled={saveLoading}
                                className={cn(
                                  'flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium transition-colors disabled:opacity-50',
                                  isModelActive
                                    ? 'bg-primary text-white'
                                    : 'bg-surface-sidebar border border-subtle text-text-secondary hover:text-primary hover:border-primary/30'
                                )}
                              >
                                {isModelActive ? <CheckCircle className="h-3 w-3" /> : <ArrowRight className="h-3 w-3" />}
                                {isModelActive ? '当前' : '设为当前'}
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-surface-main">
      {/* Header */}
      <header className="bg-surface-card border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-primary flex items-center justify-center">
              <Shield className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-text-primary">网关 & Provider</h1>
              <p className="text-xs text-text-muted">服务检测 · Provider 管理 · 模型配置 · 用量监控</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={checkServices}
              disabled={statusLoading}
              className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              检测服务
            </button>
            <button
              onClick={refresh}
              disabled={providersLoading || configLoading || usageLoading || statsLoading || healthLoading}
              className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', (providersLoading || configLoading) && 'animate-spin')} />
              刷新
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {error && (
          <div className="rounded-xl bg-status-error/5 text-status-error text-sm px-4 py-3">
            {error}
          </div>
        )}

        {/* Service Status */}
        <motion.section {...fadeIn(0.05)} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <StatusCard
            title="DialogMesh API"
            status={dmStatus}
            icon={Server}
            port=":8000"
          />
          <StatusCard
            title="Switch Gateway"
            status={swStatus}
            icon={Globe}
            port=":8080"
          />
        </motion.section>

        {/* Tabs */}
        <motion.div {...fadeIn(0.1)} className="flex gap-1 overflow-x-auto pb-1">
          {[
            { key: 'providers' as const, label: 'Provider 管理', icon: Server },
            { key: 'usage' as const, label: '用量监控', icon: Coins },
            { key: 'config' as const, label: '网关配置', icon: Settings },
            { key: 'monitor' as const, label: '监控运维', icon: Activity },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={cn(
                  'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap',
                  isActive
                    ? 'bg-primary text-white'
                    : 'bg-surface-card text-text-secondary hover:text-text-primary border border-gray-200'
                )}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </motion.div>

        {/* Providers Tab */}
        {activeTab === 'providers' && (
          <motion.section
            key="providers"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="space-y-4"
          >
            {/* Legacy Router Modes */}
            {router && (
              <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
                <div className="flex items-center gap-2 text-text-muted mb-3">
                  <Zap className="h-4 w-4" />
                  <span className="text-xs font-semibold">路由模式</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {router.modes?.map((mode) => {
                    const isActiveMode = router.active === mode.name;
                    return (
                      <div
                        key={mode.name}
                        className={cn(
                          'rounded-lg border px-3 py-2 text-xs',
                          isActiveMode ? 'border-primary bg-primary/5 text-primary' : 'border-gray-200 text-text-secondary'
                        )}
                      >
                        <span className="font-medium">{mode.name}</span>
                        <span className="ml-2 text-text-muted">{mode.complexity} · {mode.cost}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Gateway Providers */}
            <div className="space-y-3">
              {providersLoading && !gatewayProviders && (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-text-muted" />
                  <span className="ml-2 text-sm text-text-muted">加载 Provider...</span>
                </div>
              )}
              {gatewayProviders?.providers.map((provider) => (
                <ProviderCard key={provider.name} provider={provider} />
              ))}
              {gatewayProviders?.providers.length === 0 && (
                <div className="text-center py-12 text-sm text-text-muted">
                  <Server className="h-8 w-8 mx-auto mb-2" />
                  暂无 Provider 配置
                </div>
              )}
            </div>
          </motion.section>
        )}

        {/* Usage Tab */}
        {activeTab === 'usage' && (
          <motion.section
            key="usage"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="grid grid-cols-1 md:grid-cols-2 gap-4"
          >
            {/* Current Session */}
            <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <Coins className="h-4 w-4" />
                <span className="text-xs font-semibold">当前会话</span>
              </div>
              {usage?.current_session ? (
                <div className="space-y-3">
                  <div className="flex justify-between"><span className="text-sm text-text-secondary">Provider</span><span className="text-sm font-medium text-text-primary">{usage.current_session.provider}</span></div>
                  <div className="flex justify-between"><span className="text-sm text-text-secondary">模型</span><span className="text-sm font-mono text-text-primary">{usage.current_session.model}</span></div>
                  <div className="flex justify-between"><span className="text-sm text-text-secondary">轮数</span><span className="text-sm font-medium text-text-primary">{usage.current_session.turns}</span></div>
                  <div className="flex justify-between"><span className="text-sm text-text-secondary">Prompt</span><span className="text-sm font-mono text-text-primary">{usage.current_session.prompt_tokens.toLocaleString()}</span></div>
                  <div className="flex justify-between"><span className="text-sm text-text-secondary">Completion</span><span className="text-sm font-mono text-text-primary">{usage.current_session.completion_tokens.toLocaleString()}</span></div>
                  <div className="flex justify-between"><span className="text-sm text-text-secondary">估算成本</span><span className="text-sm font-medium text-primary">{usage.current_session.cost_estimate}</span></div>
                  <div className="flex justify-between"><span className="text-sm text-text-secondary">平均延迟</span><span className="text-sm text-text-primary">{usage.current_session.latency_avg_ms}ms</span></div>
                </div>
              ) : (
                <div className="text-sm text-text-secondary py-4">暂无数据</div>
              )}
            </div>

            {/* All Sessions */}
            <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <BarChart3 className="h-4 w-4" />
                <span className="text-xs font-semibold">累计用量</span>
              </div>
              {usage?.all_sessions ? (
                <div className="space-y-3">
                  <div className="flex justify-between"><span className="text-sm text-text-secondary">总 Tokens</span><span className="text-sm font-mono text-text-primary">{usage.all_sessions.total_tokens.toLocaleString()}</span></div>
                  <div className="flex justify-between"><span className="text-sm text-text-secondary">总成本</span><span className="text-sm font-medium text-primary">{usage.all_sessions.total_cost}</span></div>
                  {Object.entries(usage.all_sessions.by_provider).map(([name, data]) => (
                    <div key={name} className="rounded-lg bg-surface-sidebar p-3">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium text-text-primary">{name}</span>
                        <span className="text-sm text-primary">{data.cost}</span>
                      </div>
                      <div className="text-xs text-text-muted mt-1">{data.tokens.toLocaleString()} tokens</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-text-secondary py-4">暂无数据</div>
              )}
            </div>

            {/* Legacy Tokens */}
            {tokens && (
              <div className="bg-surface-card rounded-xl border border-gray-200 p-5 md:col-span-2">
                <div className="flex items-center gap-2 text-text-muted mb-4">
                  <Activity className="h-4 w-4" />
                  <span className="text-xs font-semibold">引擎 Token (Legacy)</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <div className="bg-surface-sidebar rounded-lg p-3">
                    <span className="text-xs text-text-muted">当前轮数</span>
                    <p className="text-lg font-semibold text-text-primary">{tokens.current?.turns || 0}</p>
                  </div>
                  <div className="bg-surface-sidebar rounded-lg p-3">
                    <span className="text-xs text-text-muted">估算 Tokens</span>
                    <p className="text-lg font-semibold text-text-primary">{(tokens.current?.est_tokens || 0).toLocaleString()}</p>
                  </div>
                  <div className="bg-surface-sidebar rounded-lg p-3">
                    <span className="text-xs text-text-muted">总会话</span>
                    <p className="text-lg font-semibold text-text-primary">{tokens.all_sessions?.count || 0}</p>
                  </div>
                  <div className="bg-surface-sidebar rounded-lg p-3">
                    <span className="text-xs text-text-muted">总计估算</span>
                    <p className="text-lg font-semibold text-text-primary">{(tokens.all_sessions?.est_tokens || 0).toLocaleString()}</p>
                  </div>
                </div>
              </div>
            )}
          </motion.section>
        )}

        {/* Config Tab */}
        {activeTab === 'config' && (
          <motion.section
            key="config"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="bg-surface-card rounded-xl border border-gray-200 p-5"
          >
            <div className="flex items-center gap-2 text-text-muted mb-4">
              <Settings className="h-4 w-4" />
              <span className="text-xs font-semibold">网关配置</span>
            </div>
            {config ? (
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-text-muted">当前 Provider</label>
                    <p className="text-sm font-medium text-text-primary">{config.active_provider}</p>
                  </div>
                  <div>
                    <label className="text-xs text-text-muted">当前模型</label>
                    <p className="text-sm font-mono text-text-primary">{config.active_model}</p>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-text-muted">降级链</label>
                  <div className="flex items-center gap-2 mt-1">
                    {config.failover_chain.map((name, idx) => (
                      <div key={name} className="flex items-center gap-2">
                        <span className="text-xs font-medium px-2 py-1 rounded bg-surface-sidebar text-text-primary">{name}</span>
                        {idx < config.failover_chain.length - 1 && <ArrowRight className="h-3 w-3 text-text-muted" />}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <label className="text-xs text-text-muted">自动故障转移</label>
                    <p className={cn('text-sm font-medium', config.auto_failover ? 'text-status-success' : 'text-text-muted')}>
                      {config.auto_failover ? '开启' : '关闭'}
                    </p>
                  </div>
                  <div>
                    <label className="text-xs text-text-muted">最大重试</label>
                    <p className="text-sm font-medium text-text-primary">{config.max_retries}</p>
                  </div>
                  <div>
                    <label className="text-xs text-text-muted">超时 (ms)</label>
                    <p className="text-sm font-medium text-text-primary">{config.timeout_ms}</p>
                  </div>
                </div>
                {config.stats && Object.entries(config.stats).length > 0 && (
                  <div className="mt-4 pt-4 border-t border-gray-100">
                    <span className="text-xs text-text-muted">Provider 统计</span>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-2">
                      {Object.entries(config.stats).map(([name, s]) => (
                        <div key={name} className="bg-surface-sidebar rounded-lg p-3">
                          <span className="text-xs text-text-muted">{name}</span>
                          <p className="text-sm font-medium text-text-primary">{s.calls} 次</p>
                          <p className="text-xs text-text-muted">{s.errors} 错误 · {s.avg_latency_ms}ms</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div className="pt-4 border-t border-gray-100">
                  <button
                    onClick={reload}
                    disabled={saveLoading}
                    className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    {saveLoading ? '重载中...' : '热重载配置'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="text-sm text-text-secondary py-4">暂无配置数据</div>
            )}
          </motion.section>
        )}

        {/* Monitor Tab */}
        {activeTab === 'monitor' && (
          <motion.section
            key="monitor"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="space-y-4"
          >
            {/* Health */}
            <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <Activity className="h-4 w-4" />
                <span className="text-xs font-semibold">健康状态</span>
              </div>
              {health ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-text-secondary">状态</span>
                    <span className={cn(
                      'text-xs font-medium px-2 py-1 rounded',
                      health.status === 'healthy' ? 'bg-status-success/10 text-status-success' : 'bg-status-error/10 text-status-error'
                    )}>
                      {health.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-text-secondary">Provider</span>
                    <span className="text-sm font-medium text-text-primary">{health.providers_healthy} / {health.providers_total} 健康</span>
                  </div>
                  {health.circuits && Object.entries(health.circuits).length > 0 && (
                    <div className="mt-2">
                      <span className="text-xs text-text-muted">断路器</span>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-1">
                        {Object.entries(health.circuits).map(([name, state]) => (
                          <div key={name} className="bg-surface-sidebar rounded-lg p-2">
                            <span className="text-xs text-text-muted">{name}</span>
                            <p className={cn(
                              'text-sm font-medium',
                              state === 'closed' ? 'text-status-success' : state === 'open' ? 'text-status-error' : 'text-status-warning'
                            )}>
                              {state}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-sm text-text-secondary py-4">暂无数据</div>
              )}
            </div>

            {/* Stats */}
            <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <BarChart3 className="h-4 w-4" />
                <span className="text-xs font-semibold">代理统计</span>
              </div>
              {stats ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div className="bg-surface-sidebar rounded-lg p-3">
                      <span className="text-xs text-text-muted">请求</span>
                      <p className="text-lg font-semibold text-text-primary">{stats.requests}</p>
                    </div>
                    <div className="bg-surface-sidebar rounded-lg p-3">
                      <span className="text-xs text-text-muted">Tokens</span>
                      <p className="text-lg font-semibold text-text-primary">{(stats.tokens || 0).toLocaleString()}</p>
                    </div>
                    <div className="bg-surface-sidebar rounded-lg p-3">
                      <span className="text-xs text-text-muted">缓存命中率</span>
                      <p className="text-lg font-semibold text-text-primary">{Math.round((stats.cache_hit_rate || 0) * 100)}%</p>
                    </div>
                    <div className="bg-surface-sidebar rounded-lg p-3">
                      <span className="text-xs text-text-muted">P95 延迟</span>
                      <p className="text-lg font-semibold text-text-primary">{stats.latency_p95}ms</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="bg-surface-sidebar rounded-lg p-2 text-center">
                      <span className="text-xs text-text-muted">P50</span>
                      <p className="text-sm font-semibold text-text-primary">{stats.latency_p50}ms</p>
                    </div>
                    <div className="bg-surface-sidebar rounded-lg p-2 text-center">
                      <span className="text-xs text-text-muted">P95</span>
                      <p className="text-sm font-semibold text-text-primary">{stats.latency_p95}ms</p>
                    </div>
                    <div className="bg-surface-sidebar rounded-lg p-2 text-center">
                      <span className="text-xs text-text-muted">P99</span>
                      <p className="text-sm font-semibold text-text-primary">{stats.latency_p99}ms</p>
                    </div>
                  </div>
                  {stats.errors_by_provider && Object.entries(stats.errors_by_provider).length > 0 && (
                    <div className="mt-2">
                      <span className="text-xs text-text-muted">错误分布</span>
                      <div className="flex gap-2 mt-1">
                        {Object.entries(stats.errors_by_provider).map(([name, count]) => (
                          <span key={name} className="text-xs text-status-error">{name}: {count}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-sm text-text-secondary py-4">暂无数据</div>
              )}
            </div>

            {/* Legacy Metrics */}
            {metrics && Object.keys(metrics).length > 0 && (
              <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
                <div className="flex items-center gap-2 text-text-muted mb-4">
                  <Activity className="h-4 w-4" />
                  <span className="text-xs font-semibold">系统指标 (Legacy)</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {Object.entries(metrics).map(([k, v]) => (
                    <div key={k} className="bg-surface-sidebar rounded-lg p-2">
                      <span className="text-xs text-text-muted">{k}</span>
                      <p className="text-sm font-medium text-text-primary">{String(v)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </motion.section>
        )}
      </div>
    </div>
  );
}
