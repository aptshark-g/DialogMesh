// FILE: src/hooks/useV6Graph.ts
// v6 Graph + DiscourseTree + Objects 数据 Hook

import { useState, useEffect, useCallback } from 'react';
import {
  getGraph,
  getDiscourseTree,
  getObjects,
} from '../api/v6';
import type {
  V6GraphResponse,
  V6DiscourseTreeResponse,
  V6ObjectsResponse,
} from '../types/api';

interface GraphData {
  graph: V6GraphResponse | null;
  discourseTree: V6DiscourseTreeResponse | null;
  objects: V6ObjectsResponse | null;
  loading: boolean;
  error: string | null;
}

// B5（2026-08-07）: 支持按会话取数 — 对话树图按当前聊天会话渲染
export function useV6Graph(sid?: string) {
  const [data, setData] = useState<GraphData>({
    graph: null,
    discourseTree: null,
    objects: null,
    loading: false,
    error: null,
  });

  const fetchAll = useCallback(async () => {
    setData(prev => ({ ...prev, loading: true, error: null }));
    try {
      const [graph, discourseTree, objects] = await Promise.all([
        getGraph(sid).catch(() => null),
        getDiscourseTree(sid).catch(() => null),
        getObjects().catch(() => null),
      ]);
      setData({ graph, discourseTree, objects, loading: false, error: null });
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取图谱失败';
      setData(prev => ({ ...prev, loading: false, error: msg }));
    }
  }, [sid]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return { ...data, refresh: fetchAll };
}
