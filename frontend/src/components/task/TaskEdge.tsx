import React from 'react';
import type { TaskNodeStatus } from '@/types/task';

interface TaskEdgeProps {
  id: string;
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  sourcePosition: 'left' | 'right' | 'top' | 'bottom';
  targetPosition: 'left' | 'right' | 'top' | 'bottom';
  label?: string;
  data?: { condition?: string; status?: TaskNodeStatus };
  style?: React.CSSProperties;
}

function computeBezierPath(
  sourceX: number,
  sourceY: number,
  sourcePosition: string,
  targetX: number,
  targetY: number,
  targetPosition: string,
): [string, number, number] {
  const distX = Math.abs(targetX - sourceX);
  const distY = Math.abs(targetY - sourceY);
  const offset = Math.max(distX, distY) * 0.5;

  let cp1x = sourceX;
  let cp1y = sourceY;
  let cp2x = targetX;
  let cp2y = targetY;

  switch (sourcePosition) {
    case 'bottom':
      cp1y += offset;
      break;
    case 'top':
      cp1y -= offset;
      break;
    case 'right':
      cp1x += offset;
      break;
    case 'left':
      cp1x -= offset;
      break;
  }

  switch (targetPosition) {
    case 'top':
      cp2y -= offset;
      break;
    case 'bottom':
      cp2y += offset;
      break;
    case 'left':
      cp2x -= offset;
      break;
    case 'right':
      cp2x += offset;
      break;
  }

  const path = `M ${sourceX},${sourceY} C ${cp1x},${cp1y} ${cp2x},${cp2y} ${targetX},${targetY}`;
  const labelX = (sourceX + targetX) / 2;
  const labelY = (sourceY + targetY) / 2;
  return [path, labelX, labelY];
}

const edgeColors: Record<TaskNodeStatus, string> = {
  pending: '#3A3548',
  running: '#D97706',
  completed: '#10B981',
  failed: '#EF4444',
  skipped: '#3A3548',
  blocked: '#3A3548',
};

export const AnimatedEdge = React.memo(function AnimatedEdge(props: TaskEdgeProps) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, data, style } = props;
  const status = data?.status || 'pending';
  const color = edgeColors[status];
  const animName = `edgeDash${id.replace(/[^a-zA-Z0-9]/g, '')}`;

  const [path, labelX, labelY] = computeBezierPath(
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  );

  return (
    <g>
      <style>{`@keyframes ${animName} { to { stroke-dashoffset: -20; } }`}</style>
      <path
        id={id}
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeDasharray="5 5"
        style={{ animation: `${animName} 1s linear infinite`, ...style }}
      />
      {label && (
        <foreignObject
          width={200}
          height={40}
          x={labelX - 100}
          y={labelY - 20}
          style={{ pointerEvents: 'none' }}
        >
          <div className="flex items-center justify-center h-full">
            <span className="text-xs text-muted bg-surface-card px-2 py-0.5 rounded-sm border border-subtle whitespace-nowrap">
              {label}
            </span>
          </div>
        </foreignObject>
      )}
    </g>
  );
});

export const ConditionEdge = React.memo(function ConditionEdge(props: TaskEdgeProps) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, data, style } = props;
  const status = data?.status || 'pending';
  const color = edgeColors[status];
  const displayLabel = data?.condition || label;

  const [path, labelX, labelY] = computeBezierPath(
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  );

  return (
    <g>
      <path id={id} d={path} fill="none" stroke={color} strokeWidth={2} style={style} />
      {displayLabel && (
        <foreignObject
          width={200}
          height={40}
          x={labelX - 100}
          y={labelY - 20}
          style={{ pointerEvents: 'none' }}
        >
          <div className="flex items-center justify-center h-full">
            <span className="text-xs text-muted bg-surface-card px-2 py-0.5 rounded-sm border border-subtle whitespace-nowrap">
              {displayLabel}
            </span>
          </div>
        </foreignObject>
      )}
    </g>
  );
});
