// FILE: src/hooks/useV6Gateway.ts
// v6 Providers + Router + Tokens + Metrics + ContextConfig 数据 Hook

import { useState, useEffect, useCallback } from 'react';
import {
  getProviders,
  getRouterModes,
  getTokens,
  getMetrics,
  testProviderConnection,
  switchProvider,
  setRouterModes,
  updateContextConfig,
} from '../api/v6';
import type {
  V6ProvidersResponse,
  V6RouterModesResponse,
  V6TokensResponse,
  V6MetricsResponse,
  V6ProviderSwitchRequest,
  V6RouterModesRequest,
  V6ContextConfigRequest,
} from '../types/api';

interface GatewayData {
  providers: V6ProvidersResponse | null;
  router: V6RouterModesResponse | null;
  tokens: V6TokensResponse | null;
  metrics: V6MetricsResponse | null;
  loading: boolean;
  error: string | null;
  testLoading: boolean;
  testResult: { healthy: boolean; latency_ms: number } | null;
  saveLoading: boolean;
  saveError: string | null;
}

export function useV6Gateway(autoRefresh: boolean = true, intervalMs: number = 8000) {
  const [data, setData] = useState<GatewayData>({
    providers: null,
    router: null,
    tokens: null,
    metrics: null,
    loading: false,
    error: null,
    testLoading: false,
    testResult: null,
    saveLoading: false,
    saveError: null,
  });

  const fetchAll = useCallback(async () => {
    setData(prev => ({ ...prev, loading: true, error: null }));
    try {
      const [providers, router, tokens, metrics] = await Promise.all([
        getProviders().catch(() => null),
        getRouterModes().catch(() => null),
        getTokens().catch(() => null),
        getMetrics().catch(() => null),
      ]);
      setData(prev => ({ ...prev, providers, router, tokens, metrics, loading: false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取网关数据失败';
      setData(prev => ({ ...prev, loading: false, error: msg }));
    }
  }, []);

  const runConnectionTest = useCallback(async () => {
    setData(prev => ({ ...prev, testLoading: true, testResult: null }));
    try {
      const result = await testProviderConnection();
      setData(prev => ({ ...prev, testLoading: false, testResult: result }));
    } catch (err) {
      setData(prev => ({
        ...prev,
        testLoading: false,
        testResult: { healthy: false, latency_ms: -1 },
      }));
    }
  }, []);

  const switchTo = useCallback(async (req: V6ProviderSwitchRequest) => {
    setData(prev => ({ ...prev, saveLoading: true, saveError: null }));
    try {
      await switchProvider(req);
      await fetchAll();
      setData(prev => ({ ...prev, saveLoading: false }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '切换 provider 失败';
      setData(prev => ({ ...prev, saveLoading: false, saveError: msg }));
    }
  }, [fetchAll]);

  const updateRouter = useCallback(async (req: V6RouterModesRequest) => {
    setData(prev => ({ ...prev, saveLoading: true, saveError: null }));
    try {
      await setRouterModes(req);
      await fetchAll();
      setData(prev => ({ ...prev, saveLoading: false }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '更新路由模式失败';
      setData(prev => ({ ...prev, saveLoading: false, saveError: msg }));
    }
  }, [fetchAll]);

  const updateContext = useCallback(async (req: V6ContextConfigRequest) => {
    setData(prev => ({ ...prev, saveLoading: true, saveError: null }));
    try {
      await updateContextConfig(req);
      await fetchAll();
      setData(prev => ({ ...prev, saveLoading: false }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '更新上下文配置失败';
      setData(prev => ({ ...prev, saveLoading: false, saveError: msg }));
    }
  }, [fetchAll]);

  useEffect(() => {
    fetchAll();
    if (!autoRefresh) return;
    const timer = setInterval(fetchAll, intervalMs);
    return () => clearInterval(timer);
  }, [fetchAll, autoRefresh, intervalMs]);

  return {
    ...data,
    refresh: fetchAll,
    runConnectionTest,
    switchTo,
    updateRouter,
    updateContext,
  };
}
