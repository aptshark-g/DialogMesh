/** SVG Flowchart Canvas — pure rendering, no business logic */
import { useState, useCallback, useRef, useEffect, useMemo } from 'react';

/* ── Types ── */
export interface FNode { id: string; label: string; x: number; y: number; w: number; h: number; type: string; }
export interface FEdge { id: string; source: string; target: string; sourceHandle: string; targetHandle: string; mode: 'auto' | 'manual'; controlPoints?: { x: number; y: number }[]; }

const HANDLES = { top: (w: number) => ({ x: w / 2, y: 0 }), bottom: (w: number, h: number) => ({ x: w / 2, y: h }),
  left: (_w: number, h: number) => ({ x: 0, y: h / 2 }), right: (w: number, h: number) => ({ x: w, y: h / 2 }),
};

export interface FlowchartCanvasProps {
  nodes: FNode[];
  edges: FEdge[];
  onNodesChange: (nodes: FNode[]) => void;
  onEdgesChange: (edges: FEdge[]) => void;
}

let _eid = 0;
const eid = (s: string, t: string) => `e_${s}_${t}_${++_eid}`;

export function FlowchartCanvas({ nodes, edges, onNodesChange, onEdgesChange }: FlowchartCanvasProps) {
  const [sel, setSel] = useState<string | null>(null);
  const [selEdge, setSelEdge] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [vx, setVx] = useState(0);
  const [vy, setVy] = useState(0);
  const [hoverNode, setHoverNode] = useState<string | null>(null);
  const [clickMode, setClickMode] = useState<'select' | 'delete'>('select');
  const [connLine, setConnLine] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [widgetOpen, setWidgetOpen] = useState(false);

  const svgRef = useRef<SVGSVGElement>(null);
  const dragNode = useRef<{ id: string; mx: number; my: number; nx: number; ny: number } | null>(null);
  const resizeNode = useRef<{ id: string; mx: number; my: number; nw: number; nh: number } | null>(null);
  const panning = useRef(false);
  const connRef = useRef<{ source: string; handle: string; sx: number; sy: number } | null>(null);

  /* ── Node drag ── */
  const onNodeDown = useCallback((e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (clickMode === 'delete') {
      onNodesChange(nodes.filter(n => n.id !== id));
      onEdgesChange(edges.filter(e => e.source !== id && e.target !== id));
      setSel(null);
      return;
    }
    const n = nodes.find(x => x.id === id); if (!n) return;
    dragNode.current = { id, mx: e.clientX, my: e.clientY, nx: n.x, ny: n.y };
    setSel(id); setSelEdge(null);
  }, [nodes, edges, clickMode, onNodesChange, onEdgesChange]);

  useEffect(() => {
    const mm = (e: MouseEvent) => {
      const d = dragNode.current; if (!d) return;
      onNodesChange(nodes.map(n => n.id === d.id ? { ...n, x: d.nx + (e.clientX - d.mx) / zoom, y: d.ny + (e.clientY - d.my) / zoom } : n));
    };
    const mu = () => { dragNode.current = null; };
    window.addEventListener('mousemove', mm); window.addEventListener('mouseup', mu);
    return () => { window.removeEventListener('mousemove', mm); window.removeEventListener('mouseup', mu); };
  }, [zoom, nodes, onNodesChange]);

  /* ── Resize ── */
  const onResizeDown = useCallback((e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    const n = nodes.find(x => x.id === id); if (!n) return;
    resizeNode.current = { id, mx: e.clientX, my: e.clientY, nw: n.w, nh: n.h };
  }, [nodes]);

  useEffect(() => {
    const mm = (e: MouseEvent) => {
      const r = resizeNode.current; if (!r) return;
      const dw = Math.max(80, Math.min(400, r.nw + (e.clientX - r.mx) / zoom));
      onNodesChange(nodes.map(n => n.id === r.id ? { ...n, w: dw, h: dw * 0.33 } : n));
    };
    const mu = () => { resizeNode.current = null; };
    window.addEventListener('mousemove', mm); window.addEventListener('mouseup', mu);
    return () => { window.removeEventListener('mousemove', mm); window.removeEventListener('mouseup', mu); };
  }, [zoom, nodes, onNodesChange]);

  /* ── Pan ── */
  const onCanvasDown = useCallback((e: React.MouseEvent) => {
    const t = e.target as Element;
    if (t.closest('[data-node]') || t.closest('[data-handle]') || t.closest('button')) return;
    panning.current = true; setSel(null); setSelEdge(null);
  }, []);
  useEffect(() => {
    if (!panning.current) return;
    const mm = (e: MouseEvent) => { setVx(v => v + e.movementX); setVy(v => v + e.movementY); };
    const mu = () => { panning.current = false; };
    window.addEventListener('mousemove', mm); window.addEventListener('mouseup', mu);
    return () => { window.removeEventListener('mousemove', mm); window.removeEventListener('mouseup', mu); };
  }, []);

  /* ── Zoom ── */
  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const rect = svgRef.current?.getBoundingClientRect(); if (!rect) return;
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const f = e.deltaY > 0 ? 0.9 : 1.11;
    setZoom(z => { const nz = Math.max(0.1, Math.min(5, z * f)); setVx(v => mx - (mx - v) * (nz / z)); setVy(v => my - (my - v) * (nz / z)); return nz; });
  }, []);

  /* ── Handle connection ── */
  const onHandleDown = useCallback((e: React.MouseEvent, nid: string, handle: string) => {
    e.stopPropagation();
    const n = nodes.find(x => x.id === nid); if (!n) return;
    const hp = HANDLES[handle as keyof typeof HANDLES](n.w, n.h);
    connRef.current = { source: nid, handle, sx: n.x + hp.x, sy: n.y + hp.y };
    setConnLine({ x1: n.x + hp.x, y1: n.y + hp.y, x2: n.x + hp.x, y2: n.y + hp.y });
  }, [nodes]);

  useEffect(() => {
    const mm = (e: MouseEvent) => {
      const c = connRef.current; if (!c) return;
      const r = svgRef.current?.getBoundingClientRect(); if (!r) return;
      setConnLine({ x1: c.sx, y1: c.sy, x2: (e.clientX - r.left + vx) / zoom, y2: (e.clientY - r.top + vy) / zoom });
    };
    const mu = (e: MouseEvent) => {
      const svgRect = svgRef.current?.getBoundingClientRect();
      if (svgRect) {
        const mx = (e.clientX - svgRect.left + vx) / zoom;
        const my = (e.clientY - svgRect.top + vy) / zoom;
        const c = connRef.current;
        if (c) {
          const target = nodes.find(n => n.id !== c.source && mx >= n.x && mx <= n.x + n.w && my >= n.y && my <= n.y + n.h);
          if (target) {
            const cx = target.x + target.w / 2, cy = target.y + target.h / 2;
            const dx = mx - cx, dy = my - cy;
            const th = Math.abs(dy) > Math.abs(dx) ? (dy > 0 ? 'top' : 'bottom') : (dx > 0 ? 'left' : 'right');
            onEdgesChange([...edges, { id: eid(c.source, target.id), source: c.source, target: target.id, sourceHandle: c.handle, targetHandle: th, mode: 'auto' }]);
          }
        }
      }
      connRef.current = null; setConnLine(null);
    };
    window.addEventListener('mousemove', mm); window.addEventListener('mouseup', mu);
    return () => { window.removeEventListener('mousemove', mm); window.removeEventListener('mouseup', mu); };
  }, [vx, vy, zoom, nodes, edges, onEdgesChange]);

  const selRef = useRef(sel);
  const selEdgeRef = useRef(selEdge);
  selRef.current = sel;
  selEdgeRef.current = selEdge;
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const edgesRef = useRef(edges);
  edgesRef.current = edges;

  /* ── Keyboard (uses refs for latest values) ── */
  useEffect(() => {
    const kd = (e: KeyboardEvent) => {
      if (e.key !== 'Delete' && e.key !== 'Backspace') return;
      const s = selRef.current;
      const se = selEdgeRef.current;
      const nds = nodesRef.current;
      const eds = edgesRef.current;
      if (s) { onNodesChange(nds.filter(n => n.id !== s)); onEdgesChange(eds.filter(e => e.source !== s && e.target !== s)); setSel(null); }
      else if (se) { onEdgesChange(eds.filter(e => e.id !== se)); setSelEdge(null); }
    };
    window.addEventListener('keydown', kd);
    return () => window.removeEventListener('keydown', kd);
  }, [onNodesChange, onEdgesChange]);

  const onEdgeClick = useCallback((e: React.MouseEvent, id: string) => {
    e.stopPropagation(); setSelEdge(id === selEdge ? null : id); setSel(null);
  }, [selEdge]);

  /* ── Edge path ── */
  const edgePath = (e: FEdge) => {
    const s = nodes.find(n => n.id === e.source), t = nodes.find(n => n.id === e.target);
    if (!s || !t) return '';
    const sh = HANDLES[e.sourceHandle as keyof typeof HANDLES](s.w, s.h);
    const th = HANDLES[e.targetHandle as keyof typeof HANDLES](t.w, t.h);
    const sx = s.x + sh.x, sy = s.y + sh.y, tx = t.x + th.x, ty = t.y + th.y;
    const dx = Math.abs(tx - sx) * 0.5;
    return `M ${sx} ${sy} C ${sx} ${sy + dx}, ${tx} ${ty - dx}, ${tx} ${ty}`;
  };

  const colorForEdge = (e: FEdge) => selEdge === e.id ? '#6366F1' : connRef.current?.source === e.source ? '#a78bfa' : '#94a3b8';

  const visibleEdges = useMemo(() =>
    (edges || []).filter(e => e && (nodes || []).some(n => n && n.id === e.source) && (nodes || []).some(n => n && n.id === e.target)),
    [edges, nodes]
  );

  const showHandles = (id: string) => sel === id || hoverNode === id;

  return (
    <div className="flex-1 overflow-hidden relative bg-[#f8f8f8] dark:bg-[#0a0a0a]">
      <div className="absolute inset-0 pointer-events-none opacity-15" style={{
        backgroundImage: 'radial-gradient(circle, #999 1px, transparent 1px)',
        backgroundSize: `${40 * zoom}px ${40 * zoom}px`, backgroundPosition: `${vx}px ${vy}px`,
      }} />
      <svg ref={svgRef} width="100%" height="100%"
        style={{ cursor: clickMode === 'delete' ? 'crosshair' : 'grab' }}
        onMouseDown={onCanvasDown} onWheel={onWheel} onClick={() => { setSel(null); setSelEdge(null); }}>
        <g transform={`translate(${vx},${vy}) scale(${zoom})`}>
          {visibleEdges.map(e => (
            <g key={e.id}>
              <path d={edgePath(e)} fill="none" stroke="transparent" strokeWidth={14}
                style={{ cursor: 'pointer' }} onClick={ev => onEdgeClick(ev, e.id)} />
              <path d={edgePath(e)} fill="none" stroke={colorForEdge(e)}
                strokeWidth={selEdge === e.id ? 2.5 : 1.8} markerEnd="url(#arrow)" />
            </g>
          ))}
          {connLine && (
            <path d={`M ${connLine.x1} ${connLine.y1} C ${connLine.x1} ${connLine.y1 + 40}, ${connLine.x2} ${connLine.y2 - 40}, ${connLine.x2} ${connLine.y2}`}
              fill="none" stroke="#6366F1" strokeWidth={2} strokeDasharray="6 3" />
          )}
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={6} markerHeight={6} orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
            </marker>
          </defs>
          {nodes.map(n => (
            <g key={n.id} data-node={n.id}
              transform={`translate(${n.x},${n.y})`}
              onMouseDown={e => onNodeDown(e, n.id)}
              onDoubleClick={() => setEditing(n.id)}
              onMouseEnter={() => setHoverNode(n.id)} onMouseLeave={() => setHoverNode(p => p === n.id ? null : p)}
              style={{ cursor: clickMode === 'delete' ? 'pointer' : 'move' }}
            >
              {showHandles(n.id) && (['top', 'bottom', 'left', 'right'] as const).map(h => {
                const hp = HANDLES[h](n.w, n.h);
                return <circle key={h} data-handle={h} data-node={n.id} cx={hp.x} cy={hp.y} r={5} fill="white" stroke="#6366F1" strokeWidth={1.5}
                  style={{ cursor: 'crosshair' }} onMouseDown={e => onHandleDown(e, n.id, h)} />;
              })}
              <rect width={n.w} height={n.h} rx={6} fill="white"
                stroke={sel === n.id ? '#6366F1' : '#94a3b8'}
                strokeWidth={sel === n.id ? 2.5 : 1.5}
                filter="drop-shadow(0 1px 3px rgba(0,0,0,0.08))" />
              {editing === n.id ? (
                <foreignObject width={n.w} height={n.h}>
                  <input autoFocus defaultValue={n.label} style={{ width: '100%', height: '100%', border: 'none', background: 'white', textAlign: 'center', fontSize: 13, fontFamily: 'system-ui, sans-serif', fontWeight: 500, outline: 'none', padding: 0, borderRadius: 6 }}
                    onBlur={e => { onNodesChange(nodes.map(x => x.id === n.id ? { ...x, label: e.target.value || '' } : x)); setEditing(null); }}
                    onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') { setEditing(null); } }} />
                </foreignObject>
              ) : (
                <text x={n.w / 2} y={n.h / 2} textAnchor="middle" dominantBaseline="central"
                  fontSize={13} fill="#1e293b" fontFamily="system-ui, sans-serif" fontWeight={500}
                  style={{ pointerEvents: 'none', userSelect: 'none' }}>{n.label || ''}</text>
              )}
              {hoverNode === n.id && (
                <circle cx={n.w} cy={n.h} r={5} fill="#6366F1" stroke="white" strokeWidth={1.5}
                  style={{ cursor: 'nwse-resize' }} onMouseDown={e => onResizeDown(e, n.id)} />
              )}
            </g>
          ))}
        </g>
      </svg>

      {/* Widget */}
      <div className="absolute top-3 left-3 z-30">
        {!widgetOpen ? (
          <button onClick={() => setWidgetOpen(true)} className="w-9 h-9 rounded-full bg-white/90 backdrop-blur border border-subtle shadow-lg flex items-center justify-center text-primary">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><line x1={12} y1={5} x2={12} y2={19} /><line x1={5} y1={12} x2={19} y2={12} /></svg>
          </button>
        ) : (
          <div className="bg-white/95 backdrop-blur border border-subtle shadow-xl rounded-lg w-44 overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 border-b border-subtle bg-surface-card/50">
              <span className="text-xs font-medium">工具</span>
              <button onClick={() => setWidgetOpen(false)} className="text-text-muted text-xs hover:text-primary">✕</button>
            </div>
            <div className="p-2 flex flex-col gap-1">
              <button onClick={() => {
                const id = `n_${Date.now()}`;
                onNodesChange([...nodes, { id, label: '', x: (400 - vx) / zoom, y: (300 - vy) / zoom, w: 130, h: 40, type: 'process' }]);
              }} className="w-full text-left px-2 py-1.5 rounded text-xs hover:bg-primary/10 text-text-secondary">+ 添加节点</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
