// FILE: src/pages/GatewayPage.tsx
// Gateway / Providers / Router / Switch 控制面板

import { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  Shield,
  Server,
  Coins,
  Activity,
  RefreshCw,
  Plug,
  CheckCircle,
  XCircle,
  Radio,
  SlidersHorizontal,
  Layers,
} from 'lucide-react';
import { useV6Gateway } from '../hooks/useV6Gateway';
import { cn } from '../lib/utils';

export function GatewayPage() {
  const {
    providers, router, tokens, metrics, loading, error,
    testLoading, testResult,
    saveLoading, saveError,
    refresh, runConnectionTest, switchTo, updateRouter,
  } = useV6Gateway(true, 8000);

  const [selectedProvider, setSelectedProvider] = useState('');
  const [selectedMode, setSelectedMode] = useState('');
  const [disableRemote, setDisableRemote] = useState(false);
  const [disableSmall, setDisableSmall] = useState(false);
  const [costBudget, setCostBudget] = useState('standard');

  const handleSwitchProvider = useCallback(() => {
    if (!selectedProvider) return;
    switchTo({ provider: selectedProvider });
  }, [selectedProvider, switchTo]);

  const handleUpdateRouter = useCallback(() => {
    const req: { mode?: string; disable_remote?: boolean; disable_small_model?: boolean; cost_budget?: string } = {};
    if (selectedMode) req.mode = selectedMode;
    req.disable_remote = disableRemote;
    req.disable_small_model = disableSmall;
    if (costBudget) req.cost_budget = costBudget;
    updateRouter(req);
  }, [selectedMode, disableRemote, disableSmall, costBudget, updateRouter]);

  const fadeIn = (delay: number) => ({
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.35, delay },
  });

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
              <p className="text-xs text-text-muted">路由切换 · Provider 管理 · Token 监控</p>
            </div>
          </div>
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            刷新
          </button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {error && (
          <div className="rounded-xl bg-status-error/5 text-status-error text-sm px-4 py-3">
            {error}
          </div>
        )}
        {saveError && (
          <div className="rounded-xl bg-status-error/5 text-status-error text-sm px-4 py-3">
            {saveError}
          </div>
        )}

        {/* Provider Status */}
        <motion.section {...fadeIn(0.05)} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 text-text-muted mb-4">
              <Server className="h-4 w-4" />
              <span className="text-xs font-semibold">当前 Provider</span>
            </div>
            {providers?.active ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">名称</span>
                  <span className="text-sm font-semibold text-text-primary">{providers.active.name}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">模型</span>
                  <span className="text-sm font-mono text-text-primary">{providers.active.model}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">健康</span>
                  <div className={cn(
                    'flex items-center gap-1 text-xs font-medium',
                    providers.active.healthy ? 'text-status-success' : 'text-status-error'
                  )}>
                    {providers.active.healthy ? <CheckCircle className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                    {providers.active.healthy ? '正常' : '异常'}
                  </div>
                </div>
                {providers.active.stats && Object.keys(providers.active.stats).length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-100">
                    <span className="text-xs text-text-muted">统计</span>
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      {Object.entries(providers.active.stats).map(([k, v]) => (
                        <div key={k} className="bg-surface-sidebar rounded-lg px-3 py-1.5">
                          <span className="text-xs text-text-muted">{k}</span>
                          <p className="text-sm font-medium text-text-primary">{String(v)}</p>
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

          <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 text-text-muted mb-4">
              <Layers className="h-4 w-4" />
              <span className="text-xs font-semibold">Failover 配置</span>
            </div>
            {providers?.failover ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">Primary</span>
                  <span className="text-sm font-medium text-text-primary">{providers.failover.primary}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">Fallback</span>
                  <span className="text-sm font-medium text-text-primary">{providers.failover.fallback}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">Active Index</span>
                  <span className="text-sm font-mono text-text-primary">{providers.failover.active_idx}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">失败次数</span>
                  <span className={cn(
                    'text-sm font-medium',
                    (providers.failover.failures || 0) > 0 ? 'text-status-error' : 'text-text-primary'
                  )}>
                    {providers.failover.failures || 0}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-sm text-text-secondary py-4">暂无数据</div>
            )}
          </div>
        </motion.section>

        {/* Router Modes */}
        <motion.section {...fadeIn(0.1)} className="bg-surface-card rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-text-muted">
              <Radio className="h-4 w-4" />
              <span className="text-xs font-semibold">路由模式</span>
            </div>
            <span className={cn(
              'text-xs font-medium px-2 py-1 rounded-md',
              router?.available ? 'bg-status-success/10 text-status-success' : 'bg-status-error/10 text-status-error'
            )}>
              {router?.available ? '可用' : '不可用'}
            </span>
          </div>

          {router?.modes && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
              {router.modes.map((mode) => {
                const isActive = router.active === mode.name;
                const isSelected = selectedMode === mode.name;
                return (
                  <button
                    key={mode.name}
                    onClick={() => setSelectedMode(mode.name)}
                    className={cn(
                      'relative rounded-lg border p-4 text-left transition-all',
                      isActive
                        ? 'border-primary bg-primary/5 ring-1 ring-primary/20'
                        : isSelected
                        ? 'border-primary/50 bg-primary/3'
                        : 'border-gray-200 hover:border-gray-300'
                    )}
                  >
                    {isActive && (
                      <span className="absolute top-2 right-2 text-xs font-medium text-primary">当前</span>
                    )}
                    <div className="text-sm font-semibold text-text-primary capitalize">{mode.name}</div>
                    <div className="mt-1 space-y-1">
                      <div className="text-xs text-text-muted">复杂度: {mode.complexity}</div>
                      <div className="text-xs text-text-muted">成本: {mode.cost}</div>
                      <div className="text-xs text-text-muted">延迟: {mode.latency}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {router?.route_stats && (
            <div className="mt-4 pt-4 border-t border-gray-100">
              <span className="text-xs text-text-muted">路由统计</span>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-2">
                {Object.entries(router.route_stats).map(([k, v]) => (
                  <div key={k} className="bg-surface-sidebar rounded-lg px-3 py-2">
                    <span className="text-xs text-text-muted">{k}</span>
                    <p className="text-lg font-semibold text-text-primary">{v}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {router?.degradation_chain && (
            <div className="mt-3 text-xs text-text-muted">
              降级链: {router.degradation_chain.join(' · ')}
            </div>
          )}

          {/* Router Controls */}
          <div className="mt-4 pt-4 border-t border-gray-100 flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-text-secondary">
              <input
                type="checkbox"
                checked={disableRemote}
                onChange={(e) => setDisableRemote(e.target.checked)}
                className="rounded border-gray-300 text-primary focus:ring-primary"
              />
              禁用 Remote
            </label>
            <label className="flex items-center gap-2 text-sm text-text-secondary">
              <input
                type="checkbox"
                checked={disableSmall}
                onChange={(e) => setDisableSmall(e.target.checked)}
                className="rounded border-gray-300 text-primary focus:ring-primary"
              />
              禁用 Small Model
            </label>
            <select
              value={costBudget}
              onChange={(e) => setCostBudget(e.target.value)}
              className="rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-xs text-text-primary focus:outline-none focus:border-primary"
            >
              <option value="standard">标准预算</option>
              <option value="free">免费模式</option>
              <option value="premium">高级预算</option>
            </select>
            <button
              onClick={handleUpdateRouter}
              disabled={saveLoading || !selectedMode}
              className="ml-auto flex items-center gap-1.5 rounded-lg bg-primary text-white px-4 py-2 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
            >
              <SlidersHorizontal className="h-3.5 w-3.5" />
              {saveLoading ? '保存中...' : '应用路由'}
            </button>
          </div>
        </motion.section>

        {/* Tokens & Test */}
        <motion.section {...fadeIn(0.15)} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 text-text-muted mb-4">
              <Coins className="h-4 w-4" />
              <span className="text-xs font-semibold">Token 消耗</span>
            </div>
            {tokens ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">当前会话</span>
                  <span className="text-sm font-medium text-text-primary">{tokens.current?.turns || 0} 轮</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">估算 Tokens</span>
                  <span className="text-sm font-mono text-text-primary">{(tokens.current?.est_tokens || 0).toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">全部会话</span>
                  <span className="text-sm font-medium text-text-primary">{tokens.all_sessions?.count || 0} 个</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-text-secondary">总计估算</span>
                  <span className="text-sm font-mono text-text-primary">{(tokens.all_sessions?.est_tokens || 0).toLocaleString()}</span>
                </div>
                {tokens.rate && Object.entries(tokens.rate).map(([provider, rate]) => (
                  <div key={provider} className="mt-2 pt-2 border-t border-gray-100">
                    <span className="text-xs text-text-muted">{provider} 费率</span>
                    <p className="text-xs font-mono text-text-secondary mt-1">{rate}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-text-secondary py-4">暂无数据</div>
            )}
          </div>

          <div className="bg-surface-card rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 text-text-muted mb-4">
              <Plug className="h-4 w-4" />
              <span className="text-xs font-semibold">连接测试</span>
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="输入 provider 名称"
                  value={selectedProvider}
                  onChange={(e) => setSelectedProvider(e.target.value)}
                  className="flex-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary"
                />
                <button
                  onClick={handleSwitchProvider}
                  disabled={saveLoading || !selectedProvider}
                  className="rounded-lg bg-primary text-white px-3 py-2 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
                >
                  切换
                </button>
              </div>
              <button
                onClick={runConnectionTest}
                disabled={testLoading}
                className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
              >
                <Activity className={cn('h-3.5 w-3.5', testLoading && 'animate-pulse')} />
                {testLoading ? '测试中...' : '测试连接'}
              </button>
              {testResult && (
                <div className={cn(
                  'rounded-lg px-3 py-2 text-sm',
                  testResult.healthy ? 'bg-status-success/10 text-status-success' : 'bg-status-error/10 text-status-error'
                )}>
                  <div className="flex items-center gap-1.5">
                    {testResult.healthy ? <CheckCircle className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                    <span className="font-medium">{testResult.healthy ? '连接正常' : '连接失败'}</span>
                  </div>
                  {testResult.healthy && (
                    <p className="text-xs mt-1">延迟: {testResult.latency_ms.toFixed(1)} ms</p>
                  )}
                </div>
              )}
            </div>
          </div>
        </motion.section>

        {/* Metrics */}
        {metrics && Object.keys(metrics).length > 0 && (
          <motion.section {...fadeIn(0.2)} className="bg-surface-card rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 text-text-muted mb-4">
              <Activity className="h-4 w-4" />
              <span className="text-xs font-semibold">系统指标</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {Object.entries(metrics).map(([k, v]) => (
                <div key={k} className="bg-surface-sidebar rounded-lg px-3 py-2">
                  <span className="text-xs text-text-muted">{k}</span>
                  <p className="text-sm font-medium text-text-primary">{String(v)}</p>
                </div>
              ))}
            </div>
          </motion.section>
        )}
      </div>
    </div>
  );
}
