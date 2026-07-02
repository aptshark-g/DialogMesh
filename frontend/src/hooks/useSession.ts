import { useState, useCallback } from 'react';
import type { CreateSessionResponse, SessionStatusResponse } from '../types/api';
import { createSession, getSessionStatus } from '../api/session';

export function useSession() {
  const [session, setSession] = useState<CreateSessionResponse | null>(null);
  const [status, setStatus] = useState<SessionStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const initSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await createSession();
      setSession(res);
      return res;
    } catch (err) {
      const msg = err instanceof Error ? err.message : '创建 Session 失败';
      setError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshStatus = useCallback(async (sessionId: string) => {
    try {
      const res = await getSessionStatus(sessionId);
      setStatus(res);
      return res;
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取状态失败';
      setError(msg);
      throw err;
    }
  }, []);

  return { session, status, loading, error, initSession, refreshStatus };
}
