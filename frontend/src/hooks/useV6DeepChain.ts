// FILE: src/hooks/useV6DeepChain.ts
// v6 Relations + Causal + Behavior + Engineering 深层链数据 Hook

import { useState, useEffect, useCallback } from 'react';
import {
  getRelations,
  getCausal,
  getBehavior,
  getEngineering,
} from '../api/v6';
import type {
  V6RelationsResponse,
  V6CausalResponse,
  V6BehaviorResponse,
  V6EngineeringResponse,
} from '../types/api';

interface DeepChainData {
  relations: V6RelationsResponse | null;
  causal: V6CausalResponse | null;
  behavior: V6BehaviorResponse | null;
  engineering: V6EngineeringResponse | null;
  loading: boolean;
  error: string | null;
}

export function useV6DeepChain() {
  const [data, setData] = useState<DeepChainData>({
    relations: null,
    causal: null,
    behavior: null,
    engineering: null,
    loading: false,
    error: null,
  });

  const fetchAll = useCallback(async () => {
    setData(prev => ({ ...prev, loading: true, error: null }));
    try {
      const [relations, causal, behavior, engineering] = await Promise.all([
        getRelations().catch(() => null),
        getCausal().catch(() => null),
        getBehavior().catch(() => null),
        getEngineering().catch(() => null),
      ]);
      setData({ relations, causal, behavior, engineering, loading: false, error: null });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取深层链数据失败';
      setData(prev => ({ ...prev, loading: false, error: msg }));
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return { ...data, refresh: fetchAll };
}
