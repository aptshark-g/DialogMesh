// FILE: src/hooks/useV6Gateway.ts
// v8 Gateway — 服务检测 + Provider 管理 + 配置 + 用量 + 运维

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
  V6GatewayProvider,
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

interface GatewayData {
  // Service status
  dmStatus: V6ServiceStatus | null;
  swStatus: V6ServiceStatus | null;
  statusLoading: boolean;

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

export function useV6Gateway(autoRefresh: boolean = true, intervalMs: number = 10000) {
  const [data, setData] = useState<GatewayData>({
    dmStatus: null,
    swStatus: null,
    statusLoading: false,
    gatewayProviders: null,
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
  const checkServices = useCallback(async () => {
    setData(prev => ({ ...prev, statusLoading: true, error: null }));
    try {
      const [dmStatus, swStatus] = await Promise.all([
        checkDialogMeshStatus().catch(() => null),
        checkSwitchGatewayStatus().catch(() => null),
      ]);
      setData(prev => ({ ...prev, dmStatus, swStatus, statusLoading: false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '检测服务状态失败';
      setData(prev => ({ ...prev, statusLoading: false, error: msg }));
    }
  }, []);

  // ─── Gateway Providers ───
  const fetchGatewayProviders = useCallback(async () => {
    setData(prev => ({ ...prev, providersLoading: true, error: null }));
    try {
      const gatewayProviders = await getGatewayProviders().catch(() => null);
      setData(prev => ({ ...prev, gatewayProviders, providersLoading: false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取 Provider 失败';
      setData(prev => ({ ...prev, providersLoading: false, error: msg }));
    }
  }, []);

  // ─── Config Provider ───
  const configProvider = useCallback(async (name: string, req: V6GatewayProviderConfigRequest) => {
    setData(prev => ({ ...prev, saveLoading: true, error: null }));
    try {
      await configGatewayProvider(name, req);
      await fetchGatewayProviders();
      setData(prev => ({ ...prev, saveLoading: false }));
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
  const fetchConfig = useCallback(async () => {
    setData(prev => ({ ...prev, configLoading: true, error: null }));
    try {
      const config = await getGatewayConfig().catch(() => null);
      setData(prev => ({ ...prev, config, configLoading: false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取配置失败';
      setData(prev => ({ ...prev, configLoading: false, error: msg }));
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
  const fetchUsage = useCallback(async () => {
    setData(prev => ({ ...prev, usageLoading: true, error: null }));
    try {
      const usage = await getGatewayUsage().catch(() => null);
      setData(prev => ({ ...prev, usage, usageLoading: false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取用量失败';
      setData(prev => ({ ...prev, usageLoading: false, error: msg }));
    }
  }, []);

  // ─── Stats ───
  const fetchStats = useCallback(async () => {
    setData(prev => ({ ...prev, statsLoading: true, error: null }));
    try {
      const stats = await getGatewayStats().catch(() => null);
      setData(prev => ({ ...prev, stats, statsLoading: false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取统计失败';
      setData(prev => ({ ...prev, statsLoading: false, error: msg }));
    }
  }, []);

  // ─── Health ───
  const fetchHealth = useCallback(async () => {
    setData(prev => ({ ...prev, healthLoading: true, error: null }));
    try {
      const health = await getGatewayHealth().catch(() => null);
      setData(prev => ({ ...prev, health, healthLoading: false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取健康状态失败';
      setData(prev => ({ ...prev, healthLoading: false, error: msg }));
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
  const fetchRouter = useCallback(async () => {
    setData(prev => ({ ...prev, routerLoading: true, error: null }));
    try {
      const router = await getRouterModes().catch(() => null);
      setData(prev => ({ ...prev, router, routerLoading: false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取路由失败';
      setData(prev => ({ ...prev, routerLoading: false, error: msg }));
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
  const fetchLegacy = useCallback(async () => {
    setData(prev => ({ ...prev, legacyLoading: true, error: null }));
    try {
      const [providers, tokens, metrics] = await Promise.all([
        getProviders().catch(() => null),
        getTokens().catch(() => null),
        getMetrics().catch(() => null),
      ]);
      setData(prev => ({ ...prev, providers, tokens, metrics, legacyLoading: false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取数据失败';
      setData(prev => ({ ...prev, legacyLoading: false, error: msg }));
    }
  }, []);

  // ─── Refresh All ───
  const refreshAll = useCallback(async () => {
    await Promise.all([
      checkServices(),
      fetchGatewayProviders(),
      fetchConfig(),
      fetchUsage(),
      fetchStats(),
      fetchHealth(),
      fetchRouter(),
      fetchLegacy(),
    ]);
  }, [checkServices, fetchGatewayProviders, fetchConfig, fetchUsage, fetchStats, fetchHealth, fetchRouter, fetchLegacy]);

  // ─── Auto Refresh ───
  useEffect(() => {
    refreshAll();
    if (!autoRefresh) return;
    intervalRef.current = setInterval(refreshAll, intervalMs);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
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
