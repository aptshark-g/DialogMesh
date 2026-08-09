/** Task Planning Page — data management + FlowchartCanvas */
import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { FlowchartCanvas } from '@/components/task/FlowchartCanvas';
import type { FNode, FEdge } from '@/components/task/FlowchartCanvas';
import { useChatStore } from '@/stores/chatStore';
import { useTaskStore } from '@/stores/taskStore';
import { getTaskGraph, saveTaskGraph, TaskGraphConflictError } from '@/api/session';
import { AlertTriangle } from 'lucide-react';

/* ── Backend JSON → Canvas nodes ── */
function apiNodesToCanvas(apiNodes: any[]): FNode[] {
  return apiNodes.map((n, i) => ({
    id: n.id || `n_${i}`,
    label: n.name || n.type || '',
    x: (i % 4) * 220 + 40,
    y: Math.floor(i / 4) * 150 + 40,
    w: 140, h: 40,
    type: n.type || 'process',
  }));
}

function canvasNodesToApi(nodes: FNode[], edges: FEdge[]): any[] {
  return nodes.map(n => ({
    id: n.id, name: n.label, type: n.type,
    dependencies: edges.filter(e => e.target === n.id).map(e => e.source),
    children: edges.filter(e => e.source === n.id).map(e => e.target),
    status: 'pending' as const, parentId: null, progress: 0,
  }));
}

function canvasEdgesToApi(edges: FEdge[]): any[] {
  return edges.map(e => ({ id: e.id, source: e.source, target: e.target, type: 'dependency' }));
}

export function TaskPlanningPage() {
  const sessionId = useChatStore(s => s.sessionId);
  const navigate = useNavigate();
  const [nodes, setNodes] = useState<FNode[]>([]);
  const [edges, setEdges] = useState<FEdge[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState<{ currentVersion: number } | null>(null);
  const versionRef = useRef(0);

  // Load from backend on mount.
  // B5（2026-08-07）: 不再用 `if (!loaded) return 加载中` 阻塞整页 —
  // 无 sessionId 时回退 default（后端对未知 session 优雅返回空），
  // 页面壳立即渲染，避免"任务页面一直在加载"。
  useEffect(() => {
    const sid = sessionId || 'default';
    let cancelled = false;
    getTaskGraph(sid)
      .then(data => {
        if (cancelled) return;
        versionRef.current = data.version ?? 0;
        const apiNodes = data.nodes || [];
        if (apiNodes.length > 0) {
          setNodes(apiNodesToCanvas(apiNodes));
          // Edges from dependencies
          const apiEdges: FEdge[] = [];
          apiNodes.forEach((n: any) => {
            (n.dependencies || []).forEach((depId: string) => {
              apiEdges.push({
                id: `e_${depId}_${n.id}`,
                source: depId, target: n.id,
                sourceHandle: 'bottom', targetHandle: 'top',
                mode: 'auto' as const,
              });
            });
          });
          setEdges(apiEdges);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, [sessionId]);

  // ── Save to backend ──
  const lastSaveRef = useRef(0);
  useEffect(() => {
    const sid = sessionId || 'default';
    if (!loaded || nodes.length === 0) return;
    const now = Date.now();
    if (now - lastSaveRef.current < 2000) return;
    lastSaveRef.current = now;
    const apiNodes = canvasNodesToApi(nodes, edges);
    const apiEdges = canvasEdgesToApi(edges);
    // Update Zustand store
    useTaskStore.getState().setTaskGraph({
      id: `tg_${sid}`, version: '1.0', nodes: apiNodes as any, edges: apiEdges as any,
      rootNodeId: apiNodes[0]?.id || '', createdAt: '', updatedAt: new Date().toISOString(),
      executionStatus: 'idle' as any, overallProgress: 0,
    });
    saveTaskGraph(sid, apiNodes, apiEdges, versionRef.current)
      .then(r => { versionRef.current = r.version ?? versionRef.current; })
      .catch((e) => {
        if (e instanceof TaskGraphConflictError) {
          setConflict({ currentVersion: e.currentVersion });
        }
      });
  }, [nodes, edges, loaded]);

  const handleExport = () => {
    const json = JSON.stringify({ nodes: canvasNodesToApi(nodes, edges), edges: canvasEdgesToApi(edges) }, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `task-graph-${sessionId?.slice(0,8) || 'export'}.json`; a.click();
  };

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const data = JSON.parse(reader.result as string);
        const apiNodes = data.nodes || [];
        if (apiNodes.length > 0) {
          setNodes(apiNodesToCanvas(apiNodes));
          const apiEdges: FEdge[] = [];
          apiNodes.forEach((n: any) => {
            (n.dependencies || []).forEach((depId: string) => {
              apiEdges.push({ id: `e_${depId}_${n.id}`, source: depId, target: n.id, sourceHandle: 'bottom', targetHandle: 'top', mode: 'auto' });
            });
          });
          setEdges(apiEdges);
        } else if (data.nodes && data.edges) {
          // Already in canvas format
          setNodes(data.nodes);
          setEdges(data.edges);
        }
      } catch { alert('JSON 格式无效'); }
    };
    reader.readAsText(file);
  };

  const handleConfirm = async () => {
    setSaving(true);
    const apiNodes = canvasNodesToApi(nodes, edges);
    const apiEdges = canvasEdgesToApi(edges);
    try {
      // 冲突未解决时确认 = 强制覆盖（不带 version）
      const r = await saveTaskGraph(sessionId!, apiNodes, apiEdges, conflict ? undefined : versionRef.current);
      versionRef.current = r.version ?? versionRef.current;
      setConflict(null);
      // Store confirmed state for next chat turn
      sessionStorage.setItem(`confirmed_tg_${sessionId}`, JSON.stringify({ nodes: apiNodes, edges: apiEdges }));
    } catch {}
    setSaving(false);
    navigate('/chat');
  };

  const handleForceOverwrite = async () => {
    const apiNodes = canvasNodesToApi(nodes, edges);
    const apiEdges = canvasEdgesToApi(edges);
    try {
      const r = await saveTaskGraph(sessionId!, apiNodes, apiEdges);
      versionRef.current = r.version ?? versionRef.current;
      setConflict(null);
    } catch {}
  };

  const handleDiscardLocal = async () => {
    if (!sessionId) return;
    try {
      const data = await getTaskGraph(sessionId);
      setNodes(apiNodesToCanvas(data.nodes || []));
      const apiEdges: FEdge[] = [];
      (data.nodes || []).forEach((n: any) => {
        (n.dependencies || []).forEach((depId: string) => {
          apiEdges.push({
            id: `e_${depId}_${n.id}`,
            source: depId, target: n.id,
            sourceHandle: 'bottom', targetHandle: 'top',
            mode: 'auto' as const,
          });
        });
      });
      setEdges(apiEdges);
      versionRef.current = data.version ?? versionRef.current;
      setConflict(null);
    } catch {}
  };

  return (
    <div className="flex flex-col h-full bg-surface">
      {conflict && (
        <div className="flex items-center gap-3 px-4 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-800 shrink-0">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span className="flex-1">
            服务端规划已更新（v{conflict.currentVersion}），你的本地编辑保留中。
          </span>
          <button onClick={handleForceOverwrite}
            className="px-2.5 py-1 rounded bg-amber-500 text-white font-medium hover:bg-amber-600">
            覆盖服务端
          </button>
          <button onClick={handleDiscardLocal}
            className="px-2.5 py-1 rounded border border-amber-300 text-amber-700 hover:bg-amber-100">
            放弃本地
          </button>
        </div>
      )}
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-subtle bg-surface-card/50 shrink-0">
        <h1 className="text-sm font-semibold text-primary">任务规划</h1>
        <div className="flex-1" />
        <span className="text-[11px] text-text-muted">{nodes.length} 节点 · {edges.length} 连线</span>
        <label className="px-3 py-1 rounded bg-surface-card border border-subtle text-text-secondary text-xs cursor-pointer hover:text-primary">
          导入 JSON
          <input type="file" accept=".json" onChange={handleImport} className="hidden" />
        </label>
        <button onClick={handleExport}
          className="px-3 py-1 rounded bg-surface-card border border-subtle text-text-secondary text-xs">导出 JSON</button>
        <button onClick={handleConfirm} disabled={saving}
          className="px-4 py-1.5 rounded bg-primary text-white text-xs font-medium hover:bg-primary/90 disabled:opacity-50">
          {saving ? '保存中...' : '✓ 确认'}
        </button>
        <button onClick={() => { setNodes([]); setEdges([]); }}
          className="px-3 py-1 rounded bg-surface-card border border-subtle text-text-secondary text-xs">清空</button>
        <button onClick={() => window.location.reload()}
          className="px-3 py-1 rounded bg-surface-card border border-subtle text-text-secondary text-xs">刷新</button>
      </div>

      {/* Canvas */}
      <FlowchartCanvas nodes={nodes} edges={edges} onNodesChange={setNodes} onEdgesChange={setEdges} />

      {/* Status bar */}
      <div className="px-4 py-1 border-t border-subtle text-[11px] text-text-muted shrink-0">
        双击节点编辑文字 | 选中后连接点拖线 | Delete删除 | 画布区域拖动平移 | 滚轮缩放
      </div>
    </div>
  );
}
