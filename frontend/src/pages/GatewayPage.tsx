// FILE: src/pages/GatewayPage.tsx
// Gateway — 服务检测 + Provider 管理 + 配置 + 用量 + 运维

import { useState, useCallback, useEffect, memo } from 'react';
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
  Plus,
  Trash2,
  Cpu,
  ArrowLeftRight,
  SlidersHorizontal,
  FlaskConical,
  Search,
} from 'lucide-react';
import { useV6Gateway } from '../hooks/useV6Gateway';
import {
  switchProvider,
  testProviderConnection,
  updateContextConfig,
  getContext,
  addGatewayProvider,
  removeGatewayProvider,
  getGatewayCost,
} from '../api/v6';
import { getStatus, triggerCheckpoint, inspectSystem } from '../api/v4';
import { cn } from '../lib/utils';
import type {
  V6GatewayProvider,
  V6GatewayModel,
  V6ProviderSwitchRequest,
  V6ProviderSwitchResponse,
  V6ContextConfigRequest,
  V6ContextResponse,
  V6GatewayProviderAddRequest,
  V6GatewayCost,
  StatusResponse,
  CheckpointResponse,
  InspectResponse,
} from '../types/api';
import { Modal } from '../components/ui/Modal';
import { Toast } from '../components/ui/Toast';
import { useUIStore } from '../stores/uiStore';


  // ─── Provider Card (memoized — only re-renders when provider data changes) ───
const ProviderCard = memo(({ provider, isExpanded, isActive, testResult, isTesting, isFetchingModels, form, activeModel, onToggle, onTest, onFetchModels, onSaveConfig, onRemove, saveLoading, removingProvider, onSetActive, onUpdateForm }:
    { provider: V6GatewayProvider; isExpanded: boolean; isActive: boolean; testResult: any; isTesting: boolean; isFetchingModels: boolean; form: {apiKey:string;baseUrl:string}; activeModel: string|undefined; onToggle: (n:string)=>void; onTest: (n:string)=>void; onFetchModels: (n:string)=>void; onSaveConfig: (n:string)=>void; onRemove: (n:string)=>void; saveLoading: boolean; removingProvider: string|null; onSetActive: (p:string,m:string)=>void; onUpdateForm: (p:string,f:string,v:string)=>void }) => (
      <div className={cn(
        'card-liquid shadow-card rounded-xl transition-colors',
        isActive ? 'border-primary ring-1 ring-primary/20' : 'border-gray-200'
      )}>
        <button
          onClick={() => onToggle(provider.name)}
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
            {isActive && activeModel && (
              <span className="text-xs text-text-muted font-mono">{activeModel}</span>
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
                        onChange={(e) => onUpdateForm(provider.name, 'apiKey', e.target.value)}
                        placeholder={provider.api_key ? '●●●●●●●● (已配置)' : '输入 API Key'}
                        className="w-full mt-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-text-muted">Base URL</label>
                      <input
                        type="text"
                        value={form.baseUrl}
                        onChange={(e) => onUpdateForm(provider.name, 'baseUrl', e.target.value)}
                        placeholder="https://api.example.com/v1"
                        className="w-full mt-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => onSaveConfig(provider.name)}
                      disabled={saveLoading}
                      className="flex items-center gap-1 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
                    >
                      <Settings className="h-3.5 w-3.5" />
                      {saveLoading ? '保存中...' : '保存'}
                    </button>
                    <button
                      onClick={() => onTest(provider.name)}
                      disabled={isTesting}
                      className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
                    >
                      {isTesting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
                      {isTesting ? '测试中...' : '测试连接'}
                    </button>
                    <button
                      onClick={() => onFetchModels(provider.name)}
                      disabled={isFetchingModels}
                      className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
                    >
                      {isFetchingModels ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Globe className="h-3.5 w-3.5" />}
                      {isFetchingModels ? '拉取中...' : '拉取模型'}
                    </button>
                    <button
                      onClick={() => onRemove(provider.name)}
                      disabled={removingProvider === provider.name}
                      className="ml-auto flex items-center gap-1 rounded-lg border border-status-error/30 px-3 py-1.5 text-xs font-medium text-status-error hover:bg-status-error/10 transition-colors disabled:opacity-50"
                    >
                      {removingProvider === provider.name ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                      删除
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
                      {(provider.models ?? []).map((model: V6GatewayModel) => {
                        const isModelActive = isActive && activeModel === model.id;
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
                                onClick={() => onSetActive(provider.name, model.id)}
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
    ));

export function GatewayPage() {
  const {
    dmStatus, swStatus, statusLoading, servicesDown,
    gatewayProviders, providersLoading,
    router,
    tokens,
    metrics,
    config, configLoading,
    usage, usageLoading,
    stats, statsLoading,
    health, healthLoading,
    error, saveLoading, fetchModelsLoading,
    refresh,
    checkServices,
    configProvider,
    testProvider,
    fetchProviderModels,
    setActive,
    reload,
  } = useV6Gateway(true, 15000);

  const [expandedProvider, setExpandedProvider] = useState<string | null>(null);
  // Persist config forms across page navigation via localStorage
  const [configForms, setConfigForms] = useState<Record<string, { apiKey: string; baseUrl: string }>>(() => {
    try {
      const saved = localStorage.getItem('dm_gateway_forms');
      return saved ? JSON.parse(saved) : {};
    } catch { return {}; }
  });
  const [testResults, setTestResults] = useState<Record<string, { healthy: boolean; latency: number; error: string | null }>>({});
  const [testingProvider, setTestingProvider] = useState<string | null>(null); // local — avoids global re-render
  const [activeTab, setActiveTab] = useState<'providers' | 'usage' | 'config' | 'monitor'>('providers');

  // ─── 网关计费（2026-08-13 接线: switch /v1/usage 真实 cost）───
  const [gatewayCost, setGatewayCost] = useState<V6GatewayCost | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => {
      getGatewayCost()
        .then((d) => { if (alive) setGatewayCost(d); })
        .catch(() => { /* 网关未启动时静默 */ });
    };
    load();
    const timer = setInterval(load, 15000);
    return () => { alive = false; clearInterval(timer); };
  }, []);

  // ─── 系统运维状态 (引擎 / Provider 切换 / 上下文配置) ───
  const [engineStatus, setEngineStatus] = useState<StatusResponse | null>(null);
  const [engineStatusLoading, setEngineStatusLoading] = useState(false);
  const [checkpointResult, setCheckpointResult] = useState<CheckpointResponse | null>(null);
  const [checkpointLoading, setCheckpointLoading] = useState(false);
  const [inspectModule, setInspectModule] = useState('');
  const [inspectResult, setInspectResult] = useState<InspectResponse | null>(null);
  const [inspectLoading, setInspectLoading] = useState(false);
  const [switchTarget, setSwitchTarget] = useState('');
  const [switchModel, setSwitchModel] = useState('');
  const [switchResult, setSwitchResult] = useState<V6ProviderSwitchResponse | null>(null);
  const [switchLoading, setSwitchLoading] = useState(false);
  const [connTest, setConnTest] = useState<{ healthy: boolean; latency_ms: number } | null>(null);
  const [connTestLoading, setConnTestLoading] = useState(false);
  const [contextData, setContextData] = useState<V6ContextResponse | null>(null);
  const [contextForm, setContextForm] = useState({
    token_budget: '',
    domain_P: '',
    domain_C: '',
    domain_K: '',
    domain_E: '',
    domain_B: '',
  });
  const [contextSaving, setContextSaving] = useState(false);

  // ─── 网关 Provider 新增/删除 ───
  const [addProviderOpen, setAddProviderOpen] = useState(false);
  const [addForm, setAddForm] = useState({ name: '', base_url: '', api_key: '', kind: '', models: '' });
  const [addLoading, setAddLoading] = useState(false);
  const [removingProvider, setRemovingProvider] = useState<string | null>(null);

  const [toast, setToast] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);
  const confirm = useUIStore((s) => s.confirm);

  // ─── 系统运维数据加载 (进入监控 tab 时) ───
  const fetchEngineStatus = useCallback(async () => {
    setEngineStatusLoading(true);
    try {
      setEngineStatus(await getStatus());
    } catch {
      setEngineStatus(null);
    } finally {
      setEngineStatusLoading(false);
    }
  }, []);

  // Auto-save config forms to localStorage
  useEffect(() => {
    try { localStorage.setItem('dm_gateway_forms', JSON.stringify(configForms)); } catch {}
  }, [configForms]);

  // Sync configForms from provider data on load (prevents key inputs from clearing on refresh)
  useEffect(() => {
    const list = gatewayProviders?.providers || [];
    if (list.length === 0) return;
    setConfigForms(prev => {
      const next = { ...prev };
      for (const p of list) {
        if (!next[p.name]) {
          next[p.name] = {
            apiKey: p.configured ? '( 已配置 )' : '',
            baseUrl: p.base_url || '',
          };
        }
      }
      return next;
    });
  }, [gatewayProviders?.providers]);

  const fetchContext = useCallback(async () => {
    try {
      setContextData(await getContext());
    } catch {
      setContextData(null);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'monitor') {
      fetchEngineStatus();
      fetchContext();
    }
  }, [activeTab, fetchEngineStatus, fetchContext]);

  // ─── 系统运维操作 ───
  const handleCheckpoint = useCallback(async () => {
    setCheckpointLoading(true);
    try {
      const resp = await triggerCheckpoint();
      setCheckpointResult(resp);
      setToast({ type: 'success', message: '深度分析已触发' });
    } catch (err) {
      setToast({ type: 'error', message: `触发失败: ${err instanceof Error ? err.message : '未知错误'}` });
    } finally {
      setCheckpointLoading(false);
    }
  }, []);

  const handleInspect = useCallback(async () => {
    const module = inspectModule.trim();
    if (!module) {
      setToast({ type: 'error', message: '请输入模块名(如 observations / hypotheses / knowledge)' });
      return;
    }
    setInspectLoading(true);
    try {
      setInspectResult(await inspectSystem(module));
    } catch (err) {
      setInspectResult(null);
      setToast({ type: 'error', message: `检查失败: ${err instanceof Error ? err.message : '未知错误'}` });
    } finally {
      setInspectLoading(false);
    }
  }, [inspectModule]);

  const handleSwitchProvider = useCallback(async () => {
    if (!switchTarget) {
      setToast({ type: 'error', message: '请选择要切换的 Provider' });
      return;
    }
    setSwitchLoading(true);
    try {
      const req: V6ProviderSwitchRequest = { provider: switchTarget };
      if (switchModel.trim()) req.model = switchModel.trim();
      const resp = await switchProvider(req);
      setSwitchResult(resp);
      setToast({
        type: resp.healthy ? 'success' : 'info',
        message: `已切换到 ${resp.switched} (${resp.model})${resp.healthy ? '' : ' · 健康检查未通过'}`,
      });
    } catch (err) {
      setSwitchResult(null);
      setToast({ type: 'error', message: `切换失败: ${err instanceof Error ? err.message : '未知错误'}` });
    } finally {
      setSwitchLoading(false);
    }
  }, [switchTarget, switchModel]);

  const handleTestConnection = useCallback(async () => {
    setConnTestLoading(true);
    try {
      setConnTest(await testProviderConnection());
    } catch (err) {
      setConnTest(null);
      setToast({ type: 'error', message: `测试失败: ${err instanceof Error ? err.message : '未知错误'}` });
    } finally {
      setConnTestLoading(false);
    }
  }, []);

  const handleSaveContext = useCallback(async () => {
    const req: V6ContextConfigRequest = {};
    const fields = [
      ['token_budget', 'Token 预算'],
      ['domain_P', 'Domain P 权重'],
      ['domain_C', 'Domain C 权重'],
      ['domain_K', 'Domain K 权重'],
      ['domain_E', 'Domain E 权重'],
      ['domain_B', 'Domain B 权重'],
    ] as const;
    for (const [key, label] of fields) {
      const raw = contextForm[key].trim();
      if (raw === '') continue;
      const value = Number(raw);
      if (Number.isNaN(value) || value < 0) {
        setToast({ type: 'error', message: `${label} 需为非负数字` });
        return;
      }
      req[key] = value;
    }
    if (Object.keys(req).length === 0) {
      setToast({ type: 'error', message: '请至少填写一项配置' });
      return;
    }
    setContextSaving(true);
    try {
      const resp = await updateContextConfig(req);
      setToast({ type: 'success', message: `已更新 ${resp.count} 项上下文配置` });
      fetchContext();
    } catch (err) {
      setToast({ type: 'error', message: `保存失败: ${err instanceof Error ? err.message : '未知错误'}` });
    } finally {
      setContextSaving(false);
    }
  }, [contextForm, fetchContext]);

  // ─── 网关 Provider 新增/删除 ───
  const handleAddProvider = useCallback(async () => {
    const name = addForm.name.trim();
    const baseUrl = addForm.base_url.trim();
    if (!name || !baseUrl) {
      setToast({ type: 'error', message: 'name 与 base_url 为必填项' });
      return;
    }
    let models: V6GatewayModel[] | undefined;
    if (addForm.models.trim()) {
      try {
        const parsed: unknown = JSON.parse(addForm.models);
        if (!Array.isArray(parsed)) throw new Error('not array');
        models = parsed as V6GatewayModel[];
      } catch {
        setToast({ type: 'error', message: 'models 需为 JSON 数组,如 [{"id":"gpt-4o","display":"GPT-4o","context":128000,"cost_in":2.5,"cost_out":10}]' });
        return;
      }
    }
    const req: V6GatewayProviderAddRequest = { name, base_url: baseUrl };
    if (addForm.api_key.trim()) req.api_key = addForm.api_key.trim();
    if (addForm.kind.trim()) req.kind = addForm.kind.trim();
    if (models) req.models = models;

    setAddLoading(true);
    try {
      const resp = await addGatewayProvider(req);
      if (resp.error) {
        setToast({ type: 'error', message: `新增失败: ${String(resp.error)}` });
      } else {
        setToast({ type: 'success', message: `Provider ${name} 已添加` });
        setAddProviderOpen(false);
        setAddForm({ name: '', base_url: '', api_key: '', kind: '', models: '' });
        refresh();
      }
    } catch (err) {
      setToast({ type: 'error', message: `新增失败: ${err instanceof Error ? err.message : '未知错误'}` });
    } finally {
      setAddLoading(false);
    }
  }, [addForm, refresh]);

  const handleRemoveProvider = useCallback((name: string) => {
    confirm({
      title: '删除 Provider',
      message: `确定删除网关 Provider「${name}」吗?该操作不可撤销。`,
      confirmText: '删除',
      onConfirm: async () => {
        setRemovingProvider(name);
        try {
          const resp = await removeGatewayProvider(name);
          if (resp.error) {
            setToast({ type: 'error', message: `删除失败: ${String(resp.error)}` });
          } else {
            setToast({ type: 'success', message: `Provider ${name} 已删除` });
            refresh();
          }
        } catch (err) {
          setToast({ type: 'error', message: `删除失败: ${err instanceof Error ? err.message : '未知错误'}` });
        } finally {
          setRemovingProvider(null);
        }
      },
    });
  }, [confirm, refresh]);

  const toggleExpand = (name: string) => {
    setExpandedProvider(prev => prev === name ? null : name);
  };

  const updateConfigForm = (name: string, field: string, value: string) => {
    const f = field as 'apiKey' | 'baseUrl';
    setConfigForms(prev => ({
      ...prev,
      [name]: { ...(prev[name] || { apiKey: '', baseUrl: '' }), [f]: value },
    }));
  };

  const handleTest = useCallback(async (name: string) => {
    setTestingProvider(name);
    const result = await testProvider(name);
    setTestingProvider(null);
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
      <div className="card-liquid shadow-card rounded-xl p-5">
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
              onClick={() => checkServices()}
              disabled={statusLoading}
              className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
            >
              <Play className="h-3.5 w-3.5" />
              检测服务
            </button>
            <button
              onClick={() => refresh()}
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
        {servicesDown && (
          <div className="rounded-xl border border-status-warning/30 bg-status-warning/10 px-4 py-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm text-status-warning">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              服务未连接,自动刷新已降频
            </div>
            <button
              onClick={() => refresh()}
              className="flex items-center gap-1 rounded-lg bg-surface-card border border-status-warning/40 px-3 py-1.5 text-xs font-medium text-status-warning hover:bg-status-warning/15 transition-colors shrink-0"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              重试
            </button>
          </div>
        )}
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
              <div className="card-liquid shadow-card rounded-xl p-5">
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
              <div className="flex items-center justify-between">
                <span className="text-xs text-text-muted">网关 Provider 列表</span>
                <button
                  onClick={() => setAddProviderOpen(true)}
                  className="flex items-center gap-1 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors"
                >
                  <Plus className="h-3.5 w-3.5" />
                  新增 Provider
                </button>
              </div>
              {providersLoading && !gatewayProviders && (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-text-muted" />
                  <span className="ml-2 text-sm text-text-muted">加载 Provider...</span>
                </div>
              )}
              {(gatewayProviders?.providers ?? []).map((provider) => (
                <ProviderCard key={provider.name} provider={provider}
                isExpanded={expandedProvider === provider.name}
                isActive={gatewayProviders?.active_provider === provider.name}
                testResult={testResults[provider.name]}
                isTesting={testingProvider === provider.name}
                isFetchingModels={fetchModelsLoading === provider.name}
                form={configForms[provider.name] || { apiKey: '', baseUrl: provider.base_url || '' }}
                activeModel={gatewayProviders?.active_model}
                onToggle={toggleExpand}
                onTest={handleTest}
                onFetchModels={handleFetchModels}
                onSaveConfig={handleSaveConfig}
                onRemove={handleRemoveProvider}
                saveLoading={saveLoading}
                removingProvider={removingProvider}
                onSetActive={handleSetActive}
                onUpdateForm={updateConfigForm} />
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
            <div className="card-liquid shadow-card rounded-xl p-5">
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
            <div className="card-liquid shadow-card rounded-xl p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <BarChart3 className="h-4 w-4" />
                <span className="text-xs font-semibold">累计用量</span>
              </div>
              {usage?.all_sessions ? (
                <div className="space-y-3">
                  <div className="flex justify-between"><span className="text-sm text-text-secondary">总 Tokens</span><span className="text-sm font-mono text-text-primary">{usage.all_sessions.total_tokens.toLocaleString()}</span></div>
                  <div className="flex justify-between"><span className="text-sm text-text-secondary">总成本</span><span className="text-sm font-medium text-primary">{usage.all_sessions.total_cost}</span></div>
                  {Object.entries(usage?.all_sessions?.by_provider ?? {}).map(([name, data]) => (
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
              <div className="card-liquid shadow-card rounded-xl p-5 md:col-span-2">
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

            {/* 网关真实统计与计费（2026-08-13: switch /v1/stats + /v1/usage）*/}
            <div className="card-liquid shadow-card rounded-xl p-5 md:col-span-2">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <Zap className="h-4 w-4" />
                <span className="text-xs font-semibold">网关真实统计与计费</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
                <div className="bg-surface-sidebar rounded-lg p-3">
                  <span className="text-xs text-text-muted">Prompt Tokens</span>
                  <p className="text-lg font-semibold text-text-primary">
                    {(stats?.tokens_prompt ?? 0).toLocaleString()}
                  </p>
                </div>
                <div className="bg-surface-sidebar rounded-lg p-3">
                  <span className="text-xs text-text-muted">Completion Tokens</span>
                  <p className="text-lg font-semibold text-text-primary">
                    {(stats?.tokens_completion ?? 0).toLocaleString()}
                  </p>
                </div>
                <div className="bg-surface-sidebar rounded-lg p-3">
                  <span className="text-xs text-text-muted">缓存命中</span>
                  <p className="text-lg font-semibold text-status-success">
                    {(stats?.cache_hits ?? 0).toLocaleString()}
                  </p>
                </div>
                <div className="bg-surface-sidebar rounded-lg p-3">
                  <span className="text-xs text-text-muted">缓存未命中</span>
                  <p className="text-lg font-semibold text-text-primary">
                    {(stats?.cache_misses ?? 0).toLocaleString()}
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="rounded-lg bg-surface-sidebar p-3">
                  <span className="text-xs text-text-muted">总费用 (USD)</span>
                  <p className="text-lg font-semibold text-primary">
                    {gatewayCost?.cost?.total?.cost_usd?.toFixed(6) ?? '-'}
                  </p>
                  <p className="text-xs text-text-muted mt-1">
                    {gatewayCost?.cost?.total?.requests ?? 0} 请求 ·{' '}
                    {(gatewayCost?.cost?.total?.prompt_tokens ?? 0).toLocaleString()} /
                    {(gatewayCost?.cost?.total?.completion_tokens ?? 0).toLocaleString()} tokens
                  </p>
                </div>
                <div className="rounded-lg bg-surface-sidebar p-3">
                  <span className="text-xs text-text-muted">按 Key 分摊</span>
                  {gatewayCost?.cost?.by_key && Object.keys(gatewayCost.cost.by_key).length > 0 ? (
                    <div className="mt-1 space-y-1">
                      {Object.entries(gatewayCost.cost.by_key).map(([k, v]) => (
                        <div key={k} className="flex justify-between text-xs">
                          <span className="text-text-secondary font-mono">{v.key}</span>
                          <span className="text-text-primary">${v.cost_usd.toFixed(6)} · {v.requests} 请求</span>
                        </div>
                      ))}
                    </div>
                  ) : <p className="text-xs text-text-muted mt-1">暂无数据</p>}
                </div>
                <div className="rounded-lg bg-surface-sidebar p-3">
                  <span className="text-xs text-text-muted">按模型分摊</span>
                  {gatewayCost?.cost?.by_model && Object.keys(gatewayCost.cost.by_model).length > 0 ? (
                    <div className="mt-1 space-y-1">
                      {Object.entries(gatewayCost.cost.by_model).map(([m, v]) => (
                        <div key={m} className="flex justify-between text-xs">
                          <span className="text-text-secondary font-mono">{v.model}</span>
                          <span className="text-text-primary">${v.cost_usd.toFixed(6)} · {v.requests} 请求</span>
                        </div>
                      ))}
                    </div>
                  ) : <p className="text-xs text-text-muted mt-1">暂无数据</p>}
                </div>
              </div>
            </div>
          </motion.section>
        )}

        {/* Config Tab */}
        {activeTab === 'config' && (
          <motion.section
            key="config"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="card-liquid shadow-card rounded-xl p-5"
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
                    {(config?.failover_chain ?? []).map((name, idx) => (
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
                {config.stats && Object.entries(config?.stats ?? {}).length > 0 && (
                  <div className="mt-4 pt-4 border-t border-gray-100">
                    <span className="text-xs text-text-muted">Provider 统计</span>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-2">
                      {Object.entries(config?.stats ?? {}).map(([name, s]) => (
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
            <div className="card-liquid shadow-card rounded-xl p-5">
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
                  {health.circuits && Object.entries(health?.circuits ?? {}).length > 0 && (
                    <div className="mt-2">
                      <span className="text-xs text-text-muted">断路器</span>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-1">
                        {Object.entries(health?.circuits ?? {}).map(([name, state]) => (
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
            <div className="card-liquid shadow-card rounded-xl p-5">
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
                      <p className="text-lg font-semibold text-text-primary">{((stats.tokens_prompt ?? 0) + (stats.tokens_completion ?? 0)).toLocaleString()}</p>
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
                  {stats.errors_by_provider && Object.entries(stats?.errors_by_provider ?? {}).length > 0 && (
                    <div className="mt-2">
                      <span className="text-xs text-text-muted">错误分布</span>
                      <div className="flex gap-2 mt-1">
                        {Object.entries(stats?.errors_by_provider ?? {}).map(([name, count]) => (
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
              <div className="card-liquid shadow-card rounded-xl p-5">
                <div className="flex items-center gap-2 text-text-muted mb-4">
                  <Activity className="h-4 w-4" />
                  <span className="text-xs font-semibold">系统指标 (Legacy)</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {Object.entries(metrics ?? {}).map(([k, v]) => (
                    <div key={k} className="bg-surface-sidebar rounded-lg p-2">
                      <span className="text-xs text-text-muted">{k}</span>
                      <p className="text-sm font-medium text-text-primary">{String(v)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ─── 系统 (引擎运维) ─── */}
            <div className="flex items-center gap-2 pt-2">
              <Cpu className="h-4 w-4 text-text-muted" />
              <span className="text-xs font-semibold text-text-muted">系统 (引擎)</span>
              <div className="flex-1 border-t border-gray-200" />
            </div>

            {/* 引擎状态 (v4/status) */}
            <div className="card-liquid shadow-card rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2 text-text-muted">
                  <Cpu className="h-4 w-4" />
                  <span className="text-xs font-semibold">引擎状态 (v4/status)</span>
                </div>
                <button
                  onClick={fetchEngineStatus}
                  disabled={engineStatusLoading}
                  className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-2.5 py-1 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={cn('h-3 w-3', engineStatusLoading && 'animate-spin')} />
                  刷新
                </button>
              </div>
              {engineStatusLoading && !engineStatus ? (
                <div className="flex items-center justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-text-muted" />
                  <span className="ml-2 text-sm text-text-muted">加载引擎状态...</span>
                </div>
              ) : engineStatus ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {(['async', 'slow', 'deep'] as const).map((engine) => (
                    <div key={engine} className="bg-surface-sidebar rounded-lg p-3">
                      <span className="text-xs font-semibold text-text-muted">{engine}</span>
                      <div className="mt-2 space-y-1">
                        {Object.entries(engineStatus?.[engine] ?? {}).map(([key, value]) => (
                          <div key={key} className="flex items-start justify-between gap-2 text-xs">
                            <span className="text-text-muted shrink-0">{key}</span>
                            <span className="text-text-primary font-mono text-right break-all">
                              {typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value)}
                            </span>
                          </div>
                        ))}
                        {Object.keys(engineStatus[engine] ?? {}).length === 0 && (
                          <div className="text-xs text-text-muted">暂无数据</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-text-secondary py-4">暂无数据</div>
              )}
            </div>

            {/* 运维操作: 深度分析 + 模块检查 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="card-liquid shadow-card rounded-xl p-5">
                <div className="flex items-center gap-2 text-text-muted mb-4">
                  <FlaskConical className="h-4 w-4" />
                  <span className="text-xs font-semibold">深度分析 (Slow Path Checkpoint)</span>
                </div>
                <button
                  onClick={handleCheckpoint}
                  disabled={checkpointLoading}
                  className="flex items-center gap-1.5 rounded-lg bg-primary text-white px-3 py-2 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
                >
                  {checkpointLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                  {checkpointLoading ? '触发中...' : '触发深度分析'}
                </button>
                {checkpointResult && (
                  <div className="mt-3 space-y-2">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-text-muted">状态</span>
                      <span className="font-medium text-text-primary">{checkpointResult.status}</span>
                    </div>
                    {checkpointResult.results && checkpointResult.results.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {(checkpointResult?.results ?? []).map((r) => (
                          <span
                            key={r.adapter}
                            className={cn(
                              'text-xs font-medium px-2 py-1 rounded',
                              r.ok ? 'bg-status-success/10 text-status-success' : 'bg-status-error/10 text-status-error'
                            )}
                          >
                            {r.adapter}: {r.ok ? 'OK' : 'FAIL'}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="card-liquid shadow-card rounded-xl p-5">
                <div className="flex items-center gap-2 text-text-muted mb-4">
                  <Search className="h-4 w-4" />
                  <span className="text-xs font-semibold">模块检查 (v4/inspect)</span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={inspectModule}
                    onChange={(e) => setInspectModule(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleInspect(); }}
                    placeholder="observations / hypotheses / knowledge..."
                    className="flex-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                  />
                  <button
                    onClick={handleInspect}
                    disabled={inspectLoading}
                    className="flex items-center gap-1 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50 shrink-0"
                  >
                    {inspectLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
                    检查
                  </button>
                </div>
                {inspectResult && (
                  <pre className="mt-3 text-xs text-text-secondary bg-surface-sidebar rounded-lg p-3 overflow-auto max-h-64">
                    {JSON.stringify(inspectResult, null, 2)}
                  </pre>
                )}
              </div>
            </div>

            {/* Provider 切换 (引擎) */}
            <div className="card-liquid shadow-card rounded-xl p-5">
              <div className="flex items-center gap-2 text-text-muted mb-4">
                <ArrowLeftRight className="h-4 w-4" />
                <span className="text-xs font-semibold">Provider 切换 (引擎)</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={switchTarget}
                  onChange={(e) => setSwitchTarget(e.target.value)}
                  className="rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                >
                  <option value="">选择 Provider</option>
                  {gatewayProviders?.providers.map((p) => (
                    <option key={p.name} value={p.name}>
                      {p.display_name} ({p.name})
                    </option>
                  ))}
                </select>
                <input
                  type="text"
                  value={switchModel}
                  onChange={(e) => setSwitchModel(e.target.value)}
                  placeholder="模型 (可选)"
                  className="rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                />
                <button
                  onClick={handleSwitchProvider}
                  disabled={switchLoading}
                  className="flex items-center gap-1 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
                >
                  {switchLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ArrowLeftRight className="h-3.5 w-3.5" />}
                  {switchLoading ? '切换中...' : '切换'}
                </button>
                <button
                  onClick={handleTestConnection}
                  disabled={connTestLoading}
                  className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
                >
                  {connTestLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
                  {connTestLoading ? '测试中...' : '测试连接'}
                </button>
              </div>
              {switchResult && (
                <div className={cn(
                  'mt-3 rounded-lg px-3 py-2 text-xs',
                  switchResult.healthy ? 'bg-status-success/10 text-status-success' : 'bg-status-warning/10 text-status-warning'
                )}>
                  当前: {switchResult.switched} · 模型 {switchResult.model} · {switchResult.healthy ? '健康' : '健康检查未通过'}
                </div>
              )}
              {connTest && (
                <div className={cn(
                  'mt-2 rounded-lg px-3 py-2 text-xs',
                  connTest.healthy ? 'bg-status-success/10 text-status-success' : 'bg-status-error/10 text-status-error'
                )}>
                  {connTest.healthy ? `✅ 连接正常 · ${connTest.latency_ms}ms` : '❌ 连接异常'}
                </div>
              )}
            </div>

            {/* 上下文配置 */}
            <div className="card-liquid shadow-card rounded-xl p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2 text-text-muted">
                  <SlidersHorizontal className="h-4 w-4" />
                  <span className="text-xs font-semibold">上下文配置</span>
                </div>
                <button
                  onClick={fetchContext}
                  className="flex items-center gap-1 rounded-lg bg-surface-sidebar border border-subtle px-2.5 py-1 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors"
                >
                  <RefreshCw className="h-3 w-3" />
                  刷新
                </button>
              </div>
              {contextData && (
                <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted">
                  {contextData.intent_category && (
                    <span>意图分类 <span className="font-medium text-primary">{contextData.intent_category}</span></span>
                  )}
                  {contextData.total_tokens !== undefined && (
                    <span>总 Tokens <span className="font-mono text-text-primary">{contextData.total_tokens.toLocaleString()}</span></span>
                  )}
                  {contextData.entries && (
                    <span>条目 <span className="font-mono text-text-primary">{contextData.entries.length}</span></span>
                  )}
                </div>
              )}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div>
                  <label className="text-xs text-text-muted">Token 预算</label>
                  <input
                    type="number"
                    min={0}
                    value={contextForm.token_budget}
                    onChange={(e) => setContextForm((prev) => ({ ...prev, token_budget: e.target.value }))}
                    placeholder="如 4096"
                    className="w-full mt-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                  />
                </div>
                {([
                  ['domain_P', 'Domain P 权重'],
                  ['domain_C', 'Domain C 权重'],
                  ['domain_K', 'Domain K 权重'],
                  ['domain_E', 'Domain E 权重'],
                  ['domain_B', 'Domain B 权重'],
                ] as const).map(([key, label]) => (
                  <div key={key}>
                    <label className="text-xs text-text-muted">{label}</label>
                    <input
                      type="number"
                      min={0}
                      step={0.05}
                      value={contextForm[key]}
                      onChange={(e) => setContextForm((prev) => ({ ...prev, [key]: e.target.value }))}
                      placeholder="如 0.2"
                      className="w-full mt-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                    />
                  </div>
                ))}
              </div>
              <div className="mt-4">
                <button
                  onClick={handleSaveContext}
                  disabled={contextSaving}
                  className="flex items-center gap-1.5 rounded-lg bg-primary text-white px-3 py-2 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
                >
                  {contextSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Settings className="h-3.5 w-3.5" />}
                  {contextSaving ? '保存中...' : '保存上下文配置'}
                </button>
              </div>
            </div>
          </motion.section>
        )}
      </div>

      {/* 新增 Provider Modal */}
      <Modal
        isOpen={addProviderOpen}
        onClose={() => setAddProviderOpen(false)}
        title="新增网关 Provider"
        footer={
          <>
            <button
              onClick={() => setAddProviderOpen(false)}
              disabled={addLoading}
              className="rounded-lg bg-surface-sidebar border border-subtle px-3 py-2 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
            >
              取消
            </button>
            <button
              onClick={handleAddProvider}
              disabled={addLoading}
              className="flex items-center gap-1 rounded-lg bg-primary text-white px-3 py-2 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
            >
              {addLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              {addLoading ? '添加中...' : '添加'}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="text-xs text-text-muted">name *</label>
            <input
              type="text"
              value={addForm.name}
              onChange={(e) => setAddForm((prev) => ({ ...prev, name: e.target.value }))}
              placeholder="如 deepseek"
              className="w-full mt-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted">base_url *</label>
            <input
              type="text"
              value={addForm.base_url}
              onChange={(e) => setAddForm((prev) => ({ ...prev, base_url: e.target.value }))}
              placeholder="https://api.example.com/v1"
              className="w-full mt-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted">api_key</label>
            <input
              type="password"
              value={addForm.api_key}
              onChange={(e) => setAddForm((prev) => ({ ...prev, api_key: e.target.value }))}
              placeholder="sk-..."
              className="w-full mt-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted">kind</label>
            <input
              type="text"
              value={addForm.kind}
              onChange={(e) => setAddForm((prev) => ({ ...prev, kind: e.target.value }))}
              placeholder="openai / ollama / lmstudio..."
              className="w-full mt-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted">models (JSON 数组,可选)</label>
            <textarea
              rows={4}
              value={addForm.models}
              onChange={(e) => setAddForm((prev) => ({ ...prev, models: e.target.value }))}
              placeholder='[{"id":"gpt-4o","display":"GPT-4o","context":128000,"cost_in":2.5,"cost_out":10}]'
              className="w-full mt-1 rounded-lg border border-gray-200 bg-surface-sidebar px-3 py-1.5 text-xs font-mono text-text-primary focus:outline-none focus:border-primary"
            />
          </div>
        </div>
      </Modal>

      {toast && (
        <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} />
      )}
    </div>
  );
}
