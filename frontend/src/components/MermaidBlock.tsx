import { useEffect, useRef, useState } from 'react';

interface MermaidBlockProps {
  chart: string;
  className?: string;
}

export function MermaidBlock({ chart, className }: MermaidBlockProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [id] = useState(`mermaid-${Math.random().toString(36).slice(2, 8)}`);

  useEffect(() => {
    if (!ref.current || !chart) return;
    import('mermaid').then((mermaid) => {
      mermaid.default.initialize({ startOnLoad: false, theme: 'dark' });
      try {
        mermaid.default.render(id, chart).then(({ svg }) => {
          if (ref.current) ref.current.innerHTML = svg;
          setError(null);
        }).catch((e: Error) => setError(e.message));
      } catch (e: any) {
        setError(e.message);
      }
    });
  }, [chart, id]);

  if (error) return <pre className="text-xs text-red-500">{error}</pre>;
  return <div ref={ref} className={className} />;
}
