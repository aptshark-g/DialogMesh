// FILE: src/hooks/useV6Sessions.ts
// v6 Sessions + Persistence 数据 Hook

import { useState, useEffect, useCallback } from 'react';
import {
  getSessions,
  getSessionData,
  getPersistence,
} from '../api/v6';
import type {
  V6SessionListItem,
  V6SessionData,
  V6PersistenceResponse,
} from '../types/api';

interface SessionsData {
  sessions: V6SessionListItem[];
  persistence: V6PersistenceResponse | null;
  loading: boolean;
  error: string | null;
}

export function useV6Sessions() {
  const [data, setData] = useState<SessionsData>({
    sessions: [],
    persistence: null,
    loading: false,
    error: null,
  });

  const fetchAll = useCallback(async () => {
    setData(prev => ({ ...prev, loading: true, error: null }));
    try {
      const [sessions, persistence] = await Promise.all([
        getSessions().catch(() => []),
        getPersistence().catch(() => null),
      ]);
      setData({ sessions, persistence, loading: false, error: null });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取会话失败';
      setData(prev => ({ ...prev, loading: false, error: msg }));
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return { ...data, refresh: fetchAll };
}

export async function fetchSessionDetail(filename: string): Promise<V6SessionData> {
  return getSessionData(filename);
}
