// FILE: frontend/src/components/analytics/WordCloud.tsx

import { useMemo, useRef, useEffect, useState } from 'react';
import { Cloud } from 'lucide-react';
import type { WordCloudData } from '../../types/analytics';
import { cn } from '../../lib/utils';

interface WordCloudProps {
  data: WordCloudData;
  className?: string;
}

interface PlacedWord {
  text: string;
  weight: number;
  color: string;
  x: number;
  y: number;
  fontSize: number;
  width: number;
  height: number;
  rotate: number;
}

function measureText(text: string, fontSize: number): { width: number; height: number } {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) return { width: text.length * fontSize * 0.6, height: fontSize };
  ctx.font = `${Math.round(fontSize)}px Inter, 'Noto Sans SC', sans-serif`;
  const metrics = ctx.measureText(text);
  return {
    width: metrics.width,
    height: fontSize * 1.2,
  };
}

function generateLayout(
  words: WordCloudData['words'],
  maxWeight: number,
  minWeight: number,
  containerWidth: number,
  containerHeight: number
): PlacedWord[] {
  if (!words.length || containerWidth <= 0 || containerHeight <= 0) return [];

  const placed: PlacedWord[] = [];
  const centerX = containerWidth / 2;
  const centerY = containerHeight / 2;

  // Sort by weight descending for spiral placement
  const sorted = [...words].sort((a, b) => b.weight - a.weight);

  const minFont = 12;
  const maxFont = Math.min(48, containerWidth / 8);

  for (const word of sorted) {
    const ratio =
      maxWeight === minWeight
        ? 0.5
        : (word.weight - minWeight) / (maxWeight - minWeight);
    const fontSize = minFont + ratio * (maxFont - minFont);
    const dims = measureText(word.text, fontSize);

    // Try spiral placement from center
    let placedWord: PlacedWord | null = null;
    const maxAttempts = 200;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const angle = 0.5 * attempt;
      const radius = 3 * attempt;
      const x = centerX + radius * Math.cos(angle) - dims.width / 2;
      const y = centerY + radius * Math.sin(angle) * 0.6 - dims.height / 2;

      // Boundary check
      if (
        x < 0 ||
        y < 0 ||
        x + dims.width > containerWidth ||
        y + dims.height > containerHeight
      ) {
        continue;
      }

      // Collision check
      let collides = false;
      for (const p of placed) {
        const pad = 4;
        if (
          x < p.x + p.width + pad &&
          x + dims.width + pad > p.x &&
          y < p.y + p.height + pad &&
          y + dims.height + pad > p.y
        ) {
          collides = true;
          break;
        }
      }

      if (!collides) {
        placedWord = {
          text: word.text,
          weight: word.weight,
          color: word.color,
          x,
          y,
          fontSize,
          width: dims.width,
          height: dims.height,
          rotate: 0,
        };
        break;
      }
    }

    if (placedWord) {
      placed.push(placedWord);
    }
  }

  return placed;
}

export function WordCloud({ data, className }: WordCloudProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const updateSize = () => {
      const rect = el.getBoundingClientRect();
      setDimensions({ width: rect.width, height: rect.height });
    };

    updateSize();

    const observer = new ResizeObserver(updateSize);
    observer.observe(el);
    window.addEventListener('resize', updateSize);

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', updateSize);
    };
  }, []);

  const placedWords = useMemo(() => {
    if (dimensions.width === 0 || dimensions.height === 0) return [];
    return generateLayout(
      data.words,
      data.maxWeight,
      data.minWeight,
      dimensions.width,
      dimensions.height
    );
  }, [data, dimensions.width, dimensions.height]);

  const hasData = data.words.length > 0;

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-primary/10">
            <Cloud className="w-4 h-4 text-primary" />
          </div>
          <h3 className="text-sm font-semibold text-text-primary">关键词云</h3>
        </div>
        <span className="text-xs text-text-muted">{data.words.length} 个关键词</span>
      </div>

      {/* Cloud Container */}
      <div
        ref={containerRef}
        className="flex-1 min-h-[240px] relative overflow-hidden rounded-lg bg-surface-card/50 border border-border-subtle"
      >
        {hasData ? (
          <svg
            width={dimensions.width}
            height={dimensions.height}
            className="absolute inset-0"
          >
            {placedWords.map((word) => (
              <text
                key={word.text}
                x={word.x + word.width / 2}
                y={word.y + word.height / 2}
                textAnchor="middle"
                dominantBaseline="central"
                fill={word.color}
                fontSize={word.fontSize}
                fontWeight={word.weight >= data.maxWeight * 0.7 ? 600 : 400}
                style={{
                  fontFamily: "Inter, 'Noto Sans SC', sans-serif",
                  cursor: 'default',
                  transition: 'opacity 200ms',
                }}
                opacity={0.85 + (word.weight / data.maxWeight) * 0.15}
              >
                {word.text}
              </text>
            ))}
          </svg>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-text-muted">
            <Cloud className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">暂无关键词数据</p>
            <p className="text-xs mt-1 opacity-60">对话内容将自动生成关键词云</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default WordCloud;
