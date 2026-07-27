/** WPS-style Flowchart DAG Editor — TODO: auto-layout + handle connection */
import { useState, useCallback, useRef, useEffect, useMemo } from 'react';

/* ── Types ── */
interface FNode { id: string; label: string; x: number; y: number; w: number; h: number; type: string; }
interface FEdge { id: string; source: string; target: string; sourceHandle: string; targetHandle: string; }

const MOCK: FNode[] = [
  { id: 'start', label: '开始', x: 300, y: 30, w: 140, h: 44, type: 'start' },
  { id: 'analyze', label: '分析需求', x: 300, y: 130, w: 140, h: 44, type: 'process' },
  { id: 'design', label: '设计方案', x: 300, y: 240, w: 140, h: 44, type: 'process' },
  { id: 'implement', label: '实现功能', x: 300, y: 350, w: 140, h: 44, type: 'process' },
  { id: 'test', label: '测试验证', x: 300, y: 460, w: 140, h: 44, type: 'process' },
  { id: 'end', label: '完成', x: 300, y: 570, w: 140, h: 44, type: 'end' },
];
const MOCK_EDGES: FEdge[] = [
  { id: 'e1', source: 'start', target: 'analyze', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'e2', source: 'analyze', target: 'design', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'e3', source: 'design', target: 'implement', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'e4', source: 'implement', target: 'test', sourceHandle: 'bottom', targetHandle: 'top' },
  { id: 'e5', source: 'test', target: 'end', sourceHandle: 'bottom', targetHandle: 'top' },
];

const HANDLE_POSITIONS: Record<string, { x: (w: number) => number; y: (h: number) => number }> = {
  top:    { x: w => w / 2, y: () => 0 },
  bottom: { x: w => w / 2, y: h => h },
  left:   { x: () => 0, y: h => h / 2 },
  right:  { x: w => w, y: h => h / 2 },
};

/* ── ID helpers ── */
let idC = 0;
const nid = () => `n_${++idC}_${Date.now()}`;
const eid = (s: string, t: string) => `e_${s}_${t}`;

/* ══════════════════════════════════════════════════════════════ */

export function TaskPlanningPage() {
  const [nodes, setNodes] = useState<FNode[]>(MOCK);
  const [edges, setEdges] = useState<FEdge[]>(MOCK_EDGES);
  const [sel, setSel] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [vx, setVx] = useState(0);
  const [vy, setVy] = useState(0);

  const svgRef = useRef<SVGSVGElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [cw, setCw] = useState(1200);
  const [ch, setCh] = useState(800);
  const dragRef = useRef<{ id: string; mx: number; my: number; nx: number; ny: number } | null>(null);
  const connRef = useRef<{ source: string; handle: string; sx: number; sy: number } | null>(null);
  const [connLine, setConnLine] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);

  // ── Resize observer ──
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => {
      setCw(e.contentRect.width);
      setCh(e.contentRect.height);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ── Node drag ──
  const onNodeDown = useCallback((e: React.MouseEvent, nid: string) => {
    e.stopPropagation();
    const n = nodes.find(x => x.id === nid);
    if (!n) return;
    dragRef.current = { id: nid, mx: e.clientX, my: e.clientY, nx: n.x, ny: n.y };
    setSel(nid);
  }, [nodes]);

  useEffect(() => {
    if (!dragRef.current) return;
    const onMove = (e: MouseEvent) => {
      const d = dragRef.current!;
      setNodes(prev => prev.map(n => n.id === d.id
        ? { ...n, x: d.nx + (e.clientX - d.mx) / zoom, y: d.ny + (e.clientY - d.my) / zoom }
        : n));
    };
    const onUp = () => { dragRef.current = null; };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, [zoom]);

  // ── Canvas pan (empty space drag) ──
  const panRef2 = useRef(false);
  const onCanvasDown = useCallback((e: React.MouseEvent) => {
    const t = e.target as SVGElement;
    if (t.closest('[data-node]') || t.closest('[data-handle]')) return;
    panRef2.current = true;
  }, []);

  useEffect(() => {
    if (!panRef2.current) return;
    const onMove = (e: MouseEvent) => {
      setVx(v => v + e.movementX);
      setVy(v => v + e.movementY);
    };
    const onUp = () => { panRef2.current = false; };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, []);

  // ── Zoom ──
  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = e.deltaY > 0 ? 0.85 : 1.18;
    setZoom(z => {
      const nz = Math.max(0.15, Math.min(4, z * factor));
      setVx(v => mx - (mx - v) * (nz / z));
      setVy(v => my - (my - v) * (nz / z));
      return nz;
    });
  }, []);

  // ── Edge creation from handle ──
  const onHandleDown = useCallback((e: React.MouseEvent, nodeId: string, handle: string) => {
    e.stopPropagation();
    const n = nodes.find(x => x.id === nodeId);
    if (!n) return;
    const hp = HANDLE_POSITIONS[handle];
    const sx = n.x + hp.x(n.w);
    const sy = n.y + hp.y(n.h);
    connRef.current = { source: nodeId, handle, sx, sy };
    setConnLine({ x1: sx, y1: sy, x2: sx, y2: sy });
  }, [nodes]);

  useEffect(() => {
    if (!connRef.current) return;
    const onMove = (e: MouseEvent) => {
      const c = connRef.current!;
      const svgRect = svgRef.current?.getBoundingClientRect();
      if (!svgRect) return;
      setConnLine({ x1: c.sx, y1: c.sy, x2: (e.clientX - svgRect.left + vx) / zoom, y2: (e.clientY - svgRect.top + vy) / zoom });
    };
    const onUp = (e: MouseEvent) => {
      const t = document.elementFromPoint(e.clientX, e.clientY);
      const handleEl = t?.closest('[data-handle]');
      if (handleEl) {
        const targetNode = handleEl.getAttribute('data-node');
        const targetHandle = handleEl.getAttribute('data-handle');
        const c = connRef.current!;
        if (targetNode && targetHandle && targetNode !== c.source) {
          setEdges(prev => [...prev, { id: eid(c.source, targetNode), source: c.source, target: targetNode, sourceHandle: c.handle, targetHandle }]);
        }
      }
      connRef.current = null;
      setConnLine(null);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, [vx, vy, zoom]);

  // ── Actions ──
  const addNode = () => {
    const id = nid();
    setNodes(prev => [...prev, { id, label: '新节点', x: (500 - vx) / zoom, y: (300 - vy) / zoom, w: 140, h: 44, type: 'process' }]);
  };
  const delNode = (id: string) => {
    setNodes(prev => prev.filter(n => n.id !== id));
    setEdges(prev => prev.filter(e => e.source !== id && e.target !== id));
    if (sel === id) setSel(null);
  };
  const delEdge = (id: string) => setEdges(prev => prev.filter(e => e.id !== id));
  const onCanvasClick = useCallback(() => setSel(null), []);

  const validEdges = edges.filter(e =>
    nodes.some(n => n.id === e.source) && nodes.some(n => n.id === e.target)
  );

  /* ── Render helpers ── */
  const handlePoint = (n: FNode, handle: string) => {
    const hp = HANDLE_POSITIONS[handle];
    return { x: hp.x(n.w), y: hp.y(n.h) };
  };
  const edgePath = (e: FEdge) => {
    const s = nodes.find(n => n.id === e.source);
    const t = nodes.find(n => n.id === e.target);
    if (!s || !t) return '';
    const sp = handlePoint(s, e.sourceHandle);
    const tp = handlePoint(t, e.targetHandle);
    const sx = s.x + sp.x, sy = s.y + sp.y;
    const tx = t.x + tp.x, ty = t.y + tp.y;
    const dx = Math.abs(tx - sx) * 0.5;
    return `M ${sx} ${sy} C ${sx} ${sy + dx}, ${tx} ${ty - dx}, ${tx} ${ty}`;
  };
  const isConn = (e: FEdge) => connRef.current?.source === e.source && connRef.current?.handle === e.sourceHandle;

  // ── Only render edges where both endpoints exist ──
  const visibleEdges = useMemo(() =>
    edges.filter(e => nodes.some(n => n.id === e.source) && nodes.some(n => n.id === e.target)),
    [edges, nodes]
  );

  return (
    <div className="flex flex-col h-full bg-surface">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-subtle bg-surface-card/50">
        <h1 className="text-sm font-semibold text-primary">流程图编辑器</h1>
        <div className="flex-1" />
        <span className="text-[11px] text-text-muted">{nodes.length} 节点 | {edges.length} 连线 | {Math.round(zoom * 100)}%</span>
        <button onClick={addNode} className="px-3 py-1 rounded bg-primary/15 text-primary text-xs font-medium hover:bg-primary/25">+ 节点</button>
        <button onClick={() => { setZoom(1); setVx(0); setVy(0); }} className="px-3 py-1 rounded bg-surface-card border border-subtle text-text-secondary text-xs hover:text-text-primary">重置视图</button>
        {sel && (
          <button onClick={() => delNode(sel)} className="px-3 py-1 rounded bg-red-500/10 text-red-500 text-xs">删除选中</button>
        )}
      </div>

      {/* Canvas */}
      <div ref={boxRef} className="flex-1 overflow-hidden bg-[#f5f5f5] dark:bg-[#0a0a0a]">
        {/* Background grid as CSS */}
        <div className="absolute inset-0 pointer-events-none opacity-15" style={{
          backgroundImage: 'radial-gradient(circle, #999 1px, transparent 1px)',
          backgroundSize: `${40 * zoom}px ${40 * zoom}px`,
          backgroundPosition: `${vx}px ${vy}px`,
        }} />
        <svg
          ref={svgRef}
          width="100%" height="100%"
          style={{ cursor: 'grab' }}
          onMouseDown={onCanvasDown}
          onWheel={onWheel}
          onClick={onCanvasClick}
        >
          <g transform={`translate(${vx},${vy}) scale(${zoom})`}>
            {/* Edges */}
            {visibleEdges.map(e => (
              <g key={e.id}>
                {/* Invisible wider hit area */}
                <path d={edgePath(e)} fill="none" stroke="transparent" strokeWidth={14}
                  style={{ cursor: 'pointer' }}
                  onClick={ev => { ev.stopPropagation(); delEdge(e.id); }} />
                <path d={edgePath(e)} fill="none"
                  stroke={isConn(e) ? '#6366F1' : '#94a3b8'}
                  strokeWidth={isConn(e) ? 2.5 : 1.8}
                  markerEnd="url(#arrow)" />
              </g>
            ))}
            {/* Temp connection line */}
            {connLine && (
              <path d={`M ${connLine.x1} ${connLine.y1} C ${connLine.x1} ${connLine.y1 + 40}, ${connLine.x2} ${connLine.y2 - 40}, ${connLine.x2} ${connLine.y2}`}
                fill="none" stroke="#6366F1" strokeWidth={2} strokeDasharray="6 3" />
            )}
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={6} markerHeight={6} orient="auto">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
              </marker>
            </defs>

            {/* Nodes */}
            {nodes.map(n => (
              <g key={n.id} data-node={n.id}
                transform={`translate(${n.x},${n.y})`}
                onMouseDown={e => onNodeDown(e, n.id)}
                style={{ cursor: 'move' }}
              >
                {/* Handles (connection points) */}
                {['top', 'bottom', 'left', 'right'].map(h => {
                  const hp = HANDLE_POSITIONS[h];
                  return (
                    <circle key={h} data-handle={h} data-node={n.id}
                      cx={hp.x(n.w)} cy={hp.y(n.h)} r={5}
                      fill="white" stroke={sel === n.id ? '#6366F1' : '#94a3b8'} strokeWidth={1.5}
                      style={{ cursor: 'crosshair', opacity: sel === n.id ? 1 : 0 }}
                      className="transition-opacity hover:!opacity-100"
                      onMouseDown={e => onHandleDown(e, n.id, h)}
                    />
                  );
                })}

                {/* Node body */}
                <rect width={n.w} height={n.h} rx={6}
                  fill="white" stroke={sel === n.id ? '#6366F1' : n.type === 'start' || n.type === 'end' ? '#10B981' : '#94a3b8'}
                  strokeWidth={sel === n.id ? 2.5 : 1.5}
                  filter="drop-shadow(0 1px 3px rgba(0,0,0,0.08))"
                />
                <text x={n.w / 2} y={n.h / 2} textAnchor="middle" dominantBaseline="central"
                  fontSize={13} fill="#1e293b" fontFamily="system-ui, sans-serif" fontWeight={500}
                  style={{ pointerEvents: 'none', userSelect: 'none' }}
                >{n.label}</text>
              </g>
            ))}
          </g>
        </svg>
      </div>
    </div>
  );
}
