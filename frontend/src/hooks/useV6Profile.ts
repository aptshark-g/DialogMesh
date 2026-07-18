// FILE: src/hooks/useV6Profile.ts
// v6 Profile + Trace + ABC + Mind 数据 Hook

import { useState, useEffect, useCallback } from 'react';
import {
  getProfile,
  getTrace,
  getAbc,
  getMind,
} from '../api/v6';
import type {
  V6ProfileResponse,
  V6TraceResponse,
  V6AbcResponse,
  V6MindResponse,
} from '../types/api';

interface ProfileData {
  profile: V6ProfileResponse | null;
  trace: V6TraceResponse | null;
  abc: V6AbcResponse | null;
  mind: V6MindResponse | null;
  loading: boolean;
  error: string | null;
}

export function useV6Profile(autoRefresh: boolean = false, intervalMs: number = 5000) {
  const [data, setData] = useState<ProfileData>({
    profile: null,
    trace: null,
    abc: null,
    mind: null,
    loading: false,
    error: null,
  });

  const fetchAll = useCallback(async () => {
    setData(prev => ({ ...prev, loading: true, error: null }));
    try {
      const [profile, trace, abc, mind] = await Promise.all([
        getProfile().catch(() => null),
        getTrace().catch(() => null),
        getAbc().catch(() => null),
        getMind().catch(() => null),
      ]);
      setData({ profile, trace, abc, mind, loading: false, error: null });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取画像失败';
      setData(prev => ({ ...prev, loading: false, error: msg }));
    }
  }, []);

  useEffect(() => {
    fetchAll();
    if (!autoRefresh) return;
    const timer = setInterval(fetchAll, intervalMs);
    return () => clearInterval(timer);
  }, [fetchAll, autoRefresh, intervalMs]);

  return { ...data, refresh: fetchAll };
}
