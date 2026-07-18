// FILE: src/hooks/useV6Pipeline.ts
// v6 Pipeline + Extraction + Perspectives + Parameters + Context 数据 Hook

import { useState, useEffect, useCallback } from 'react';
import {
  getPipeline,
  getExtraction,
  getPerspectives,
  getParameters,
  editParameters,
  getContext,
} from '../api/v6';
import type {
  V6PipelineResponse,
  V6ExtractionResponse,
  V6PerspectivesResponse,
  V6ParametersResponse,
  V6ParameterEditRequest,
  V6ContextResponse,
} from '../types/api';

interface PipelineData {
  pipeline: V6PipelineResponse | null;
  extraction: V6ExtractionResponse | null;
  perspectives: V6PerspectivesResponse | null;
  parameters: V6ParametersResponse | null;
  context: V6ContextResponse | null;
  loading: boolean;
  error: string | null;
  saveLoading: boolean;
  saveError: string | null;
}

export function useV6Pipeline(autoRefresh: boolean = true, intervalMs: number = 10000) {
  const [data, setData] = useState<PipelineData>({
    pipeline: null,
    extraction: null,
    perspectives: null,
    parameters: null,
    context: null,
    loading: false,
    error: null,
    saveLoading: false,
    saveError: null,
  });

  const fetchAll = useCallback(async () => {
    setData(prev => ({ ...prev, loading: true, error: null }));
    try {
      const [pipeline, extraction, perspectives, parameters, context] = await Promise.all([
        getPipeline().catch(() => null),
        getExtraction().catch(() => null),
        getPerspectives().catch(() => null),
        getParameters().catch(() => null),
        getContext().catch(() => null),
      ]);
      setData(prev => ({ ...prev, pipeline, extraction, perspectives, parameters, context, loading: false, error: null }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取管道数据失败';
      setData(prev => ({ ...prev, loading: false, error: msg }));
    }
  }, []);

  const editParams = useCallback(async (req: V6ParameterEditRequest) => {
    setData(prev => ({ ...prev, saveLoading: true, saveError: null }));
    try {
      await editParameters(req);
      await fetchAll();
      setData(prev => ({ ...prev, saveLoading: false }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : '修改参数失败';
      setData(prev => ({ ...prev, saveLoading: false, saveError: msg }));
    }
  }, [fetchAll]);

  useEffect(() => {
    fetchAll();
    if (!autoRefresh) return;
    const timer = setInterval(fetchAll, intervalMs);
    return () => clearInterval(timer);
  }, [fetchAll, autoRefresh, intervalMs]);

  return { ...data, refresh: fetchAll, editParams };
}
