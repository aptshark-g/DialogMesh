// FILE: src/hooks/useV6Gateway.ts
// v8 Gateway — 服务检测 + Provider 管理 + 配置 + 用量 + 运维
// 轮询策略: 服务探测级联 + 后台静默刷新(不切换 Loading 标志) + 页面隐藏时暂停

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  checkDialogMeshStatus,
  checkSwitchGatewayStatus,
  getGatewayProviders,
  configGatewayProvider,
  testGatewayProvider,
  fetchGatewayProviderModels,
  setGatewayActive,
  getGatewayConfig,
  updateGatewayConfig,
  getGatewayUsage,
  getGatewayStats,
  getGatewayHealth,
  reloadGateway,
  getRouterModes,
  setRouterModes,
  getProviders,
  getTokens,
  getMetrics,
} from '../api/v6';
import type {
  V6GatewayProvidersResponse,
  V6GatewayProviderConfigRequest,
  V6GatewayTestResponse,
  V6GatewayModelsResponse,
  V6GatewayActiveRequest,
  V6GatewayConfig,
  V6GatewayConfigRequest,
  V6GatewayUsage,
  V6GatewayStats,
  V6GatewayHealth,
  V6ServiceStatus,
  V6RouterModesResponse,
  V6ProvidersResponse,
  V6TokensResponse,
  V6MetricsResponse,
} from '../types/api';

interface FetchOptions {
  /** 后台轮询: 不切换 *Loading 标志,避免骨架屏闪烁 */
  background?: boolean;
}

interface GatewayData {
  // Service status
  dmStatus: V6ServiceStatus | null;
  swStatus: V6ServiceStatus | null;
  statusLoading: boolean;
  /** DialogMesh API 与 Switch Gateway 均不可达 */
  servicesDown: boolean;

  // Gateway providers
  gatewayProviders: V6GatewayProvidersResponse | null;
  providersLoading: boolean;

  // Router (legacy)
  router: V6RouterModesResponse | null;
  routerLoading: boolean;

  // Legacy providers
  providers: V6ProvidersResponse | null;
  tokens: V6TokensResponse | null;
  metrics: V6MetricsResponse | null;
  legacyLoading: boolean;

  // Gateway config
  config: V6GatewayConfig | null;
  configLoading: boolean;

  // Gateway usage
  usage: V6GatewayUsage | null;
  usageLoading: boolean;

  // Gateway stats
  stats: V6GatewayStats | null;
  statsLoading: boolean;

  // Gateway health
  health: V6GatewayHealth | null;
  healthLoading: boolean;

  // Actions
  error: string | null;
  saveLoading: boolean;
  testLoading: string | null; // provider name being tested
  fetchModelsLoading: string | null; // provider name being fetched
}

export function useV6Gateway(autoRefresh: boolean = true, intervalMs: number = 15000) {
  const [data, setData] = useState<GatewayData>({
    dmStatus: null,
    swStatus: null,
    statusLoading: false,
    servicesDown: false,
    gatewayProviders: null, // 首次拉取失败时才用 DEFAULT_PROVIDERS 兜底
    providersLoading: false,
    router: null,
    routerLoading: false,
    providers: null,
    tokens: null,
    metrics: null,
    legacyLoading: false,
    config: null,
    configLoading: false,
    usage: null,
    usageLoading: false,
    stats: null,
    statsLoading: false,
    health: null,
    healthLoading: false,
    error: null,
    saveLoading: false,
    testLoading: null,
    fetchModelsLoading: null,
  });

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─── Service Status Detection ───
  const checkServices = useCallback(async (opts?: FetchOptions): Promise<[V6ServiceStatus | null, V6ServiceStatus | null]> => {
    const bg = opts?.background === true;
    if (!bg) setData(prev => ({ ...prev, statusLoading: true, error: null }));
    // checkServiceStatus 内部不抛异常,不可达时返回 healthy: false
    const result: [V6ServiceStatus | null, V6ServiceStatus | null] = await Promise.all([
      checkDialogMeshStatus().catch(() => null),
      checkSwitchGatewayStatus().catch(() => null),
    ]);
    const [dmStatus, swStatus] = result;
    setData(prev => ({ ...prev, dmStatus, swStatus, statusLoading: bg ? prev.statusLoading : false, error: null }));
    return result;
  }, []);

  // ─── Gateway Providers ───
  const fetchGatewayProviders = useCallback(async (opts?: FetchOptions) => {
    const bg = opts?.background === true;
    if (!bg) setData(prev => ({ ...prev, providersLoading: true, error: null }));
    try {
      const gatewayProviders = await getGatewayProviders();
      setData(prev => {
        // Skip update if data unchanged (prevents full re-render jitter on auto-refresh)
        if (JSON.stringify(prev.gatewayProviders) === JSON.stringify(gatewayProviders)) {
          return { ...prev, providersLoading: bg ? prev.providersLoading : false };
        }
        return { ...prev, gatewayProviders, providersLoading: bg ? prev.providersLoading : false, error: null };
      });
    } catch {
      setData(prev => ({
        ...prev,
        providersLoading: bg ? prev.providersLoading : false,
        error: null,
      }));
    }
  }, []);

  // ─── Config Provider ───
  const configProvider = useCallback(async (name: string, req: V6GatewayProviderConfigRequest) => {
    setData(prev => ({ ...prev, saveLoading: true, error: null }));
    try {
      await configGatewayProvider(name, req);
      // Don't reload full list — just mark saved locally
      setData(prev => ({
        ...prev,
        saveLoading: false,
        gatewayProviders: prev.gatewayProviders ? {
          ...prev.gatewayProviders,
          providers: (prev.gatewayProviders as any).providers?.map((p: any) =>
            p.name === name ? { ...p, configured: true } : p
          ),
        } : prev.gatewayProviders,
      }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '配置 Provider 失败';
      setData(prev => ({ ...prev, saveLoading: false, error: msg }));
    }
  }, [fetchGatewayProviders]);

  // ─── Test Provider ───
  const testProvider = useCallback(async (name: string): Promise<V6GatewayTestResponse | null> => {
    setData(prev => ({ ...prev, testLoading: name, error: null }));
    try {
      const result = await testGatewayProvider(name);
      setData(prev => ({ ...prev, testLoading: null }));
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : '测试连接失败';
      setData(prev => ({ ...prev, testLoading: null, error: msg }));
      return null;
    }
  }, []);

  // ─── Fetch Provider Models ───
  const fetchProviderModels = useCallback(async (name: string): Promise<V6GatewayModelsResponse | null> => {
    setData(prev => ({ ...prev, fetchModelsLoading: name, error: null }));
    try {
      const result = await fetchGatewayProviderModels(name);
      await fetchGatewayProviders(); // Refresh provider list with new models
      setData(prev => ({ ...prev, fetchModelsLoading: null }));
      return result;
    } catch (err) {
      const msg = err instanceof Error ? err.message : '拉取模型失败';
      setData(prev => ({ ...prev, fetchModelsLoading: null, error: msg }));
      return null;
    }
  }, [fetchGatewayProviders]);

  // ─── Set Active ───
  const setActive = useCallback(async (req: V6GatewayActiveRequest) => {
    setData(prev => ({ ...prev, saveLoading: true, error: null }));
    try {
      await setGatewayActive(req);
      await fetchGatewayProviders();
      setData(prev => ({ ...prev, saveLoading: false }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '切换模型失败';
      setData(prev => ({ ...prev, saveLoading: false, error: msg }));
    }
  }, [fetchGatewayProviders]);

  // ─── Gateway Config ───
  const fetchConfig = useCallback(async (opts?: FetchOptions) => {
    const bg = opts?.background === true;
    if (!bg) setData(prev => ({ ...prev, configLoading: true, error: null }));
    try {
      const config = await getGatewayConfig().catch(() => null);
      setData(prev => ({ ...prev, config, configLoading: bg ? prev.configLoading : false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取配置失败';
      setData(prev => ({ ...prev, configLoading: bg ? prev.configLoading : false, error: msg }));
    }
  }, []);

  const updateConfig = useCallback(async (req: V6GatewayConfigRequest) => {
    setData(prev => ({ ...prev, saveLoading: true, error: null }));
    try {
      await updateGatewayConfig(req);
      await fetchConfig();
      setData(prev => ({ ...prev, saveLoading: false }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '更新配置失败';
      setData(prev => ({ ...prev, saveLoading: false, error: msg }));
    }
  }, [fetchConfig]);

  // ─── Usage ───
  const fetchUsage = useCallback(async (opts?: FetchOptions) => {
    const bg = opts?.background === true;
    if (!bg) setData(prev => ({ ...prev, usageLoading: true, error: null }));
    try {
      const usage = await getGatewayUsage().catch(() => null);
      setData(prev => ({ ...prev, usage, usageLoading: bg ? prev.usageLoading : false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取用量失败';
      setData(prev => ({ ...prev, usageLoading: bg ? prev.usageLoading : false, error: msg }));
    }
  }, []);

  // ─── Stats ───
  const fetchStats = useCallback(async (opts?: FetchOptions) => {
    const bg = opts?.background === true;
    if (!bg) setData(prev => ({ ...prev, statsLoading: true, error: null }));
    try {
      const stats = await getGatewayStats().catch(() => null);
      setData(prev => ({ ...prev, stats, statsLoading: bg ? prev.statsLoading : false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取统计失败';
      setData(prev => ({ ...prev, statsLoading: bg ? prev.statsLoading : false, error: msg }));
    }
  }, []);

  // ─── Health ───
  const fetchHealth = useCallback(async (opts?: FetchOptions) => {
    const bg = opts?.background === true;
    if (!bg) setData(prev => ({ ...prev, healthLoading: true, error: null }));
    try {
      const health = await getGatewayHealth().catch(() => null);
      setData(prev => ({ ...prev, health, healthLoading: bg ? prev.healthLoading : false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取健康状态失败';
      setData(prev => ({ ...prev, healthLoading: bg ? prev.healthLoading : false, error: msg }));
    }
  }, []);

  // ─── Reload ───
  const reload = useCallback(async () => {
    setData(prev => ({ ...prev, saveLoading: true, error: null }));
    try {
      await reloadGateway();
      await Promise.all([fetchGatewayProviders(), fetchConfig(), fetchHealth()]);
      setData(prev => ({ ...prev, saveLoading: false }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '重载失败';
      setData(prev => ({ ...prev, saveLoading: false, error: msg }));
    }
  }, [fetchGatewayProviders, fetchConfig, fetchHealth]);

  // ─── Legacy Router ───
  const fetchRouter = useCallback(async (opts?: FetchOptions) => {
    const bg = opts?.background === true;
    if (!bg) setData(prev => ({ ...prev, routerLoading: true, error: null }));
    try {
      const router = await getRouterModes().catch(() => null);
      setData(prev => ({ ...prev, router, routerLoading: bg ? prev.routerLoading : false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取路由失败';
      setData(prev => ({ ...prev, routerLoading: bg ? prev.routerLoading : false, error: msg }));
    }
  }, []);

  const updateRouter = useCallback(async (req: { mode?: string; disable_remote?: boolean; disable_small_model?: boolean; cost_budget?: string }) => {
    setData(prev => ({ ...prev, saveLoading: true, error: null }));
    try {
      await setRouterModes(req);
      await fetchRouter();
      setData(prev => ({ ...prev, saveLoading: false }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '更新路由失败';
      setData(prev => ({ ...prev, saveLoading: false, error: msg }));
    }
  }, [fetchRouter]);

  // ─── Legacy Providers ───
  const fetchLegacy = useCallback(async (opts?: FetchOptions) => {
    const bg = opts?.background === true;
    if (!bg) setData(prev => ({ ...prev, legacyLoading: true, error: null }));
    try {
      const [providers, tokens, metrics] = await Promise.all([
        getProviders().catch(() => null),
        getTokens().catch(() => null),
        getMetrics().catch(() => null),
      ]);
      setData(prev => ({ ...prev, providers, tokens, metrics, legacyLoading: bg ? prev.legacyLoading : false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取数据失败';
      setData(prev => ({ ...prev, legacyLoading: bg ? prev.legacyLoading : false, error: msg }));
    }
  }, []);

  // ─── Refresh All (服务探测级联) ───
  const refreshAll = useCallback(async (opts?: FetchOptions) => {
    // 每轮先探测服务; 双服务不可达则跳过其余数据请求
    const [dmStatus, swStatus] = await checkServices(opts);
    if (!dmStatus?.healthy && !swStatus?.healthy) {
      setData(prev => ({
        ...prev,
        servicesDown: true,
      }));
      return;
    }
    setData(prev => ({ ...prev, servicesDown: false }));
    await Promise.all([
      fetchGatewayProviders(opts),
      fetchConfig(opts),
      fetchUsage(opts),
      fetchStats(opts),
      fetchHealth(opts),
      fetchRouter(opts),
      fetchLegacy(opts),
    ]);
  }, [checkServices, fetchGatewayProviders, fetchConfig, fetchUsage, fetchStats, fetchHealth, fetchRouter, fetchLegacy]);

  // ─── Auto Refresh (页面隐藏时暂停,恢复可见立即刷新一次) ───
  useEffect(() => {
    refreshAll(); // 首次前台加载
    if (!autoRefresh) return;

    const stopTimer = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
    const startTimer = () => {
      stopTimer();
      intervalRef.current = setInterval(() => {
        refreshAll({ background: true });
      }, intervalMs);
    };
    const handleVisibility = () => {
      if (document.hidden) {
        stopTimer();
      } else {
        refreshAll({ background: true });
        startTimer();
      }
    };

    if (!document.hidden) startTimer();
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      stopTimer();
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [refreshAll, autoRefresh, intervalMs]);

  return {
    ...data,
    refresh: refreshAll,
    checkServices,
    configProvider,
    testProvider,
    fetchProviderModels,
    setActive,
    updateConfig,
    reload,
    updateRouter,
  };
}
