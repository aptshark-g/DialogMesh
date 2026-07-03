import React, { useCallback } from 'react';

interface IntentTagProps {
  intent: string;
  onClick?: () => void;
}

const intentColorMap: Record<string, string> = {
  'SCAN_MEMORY': '#D97706',      // amber
  'READ_MEMORY': '#0D9488',      // teal
  'WRITE_MEMORY': '#8B5CF6',     // violet
  'HACK_VALUE': '#E11D48',       // rose
  'EXPLAIN': '#3B82F6',          // blue
  'PROVIDE_CODE': '#10B981',     // emerald
  'UNKNOWN': '#6B6680',          // gray
};

function getIntentColor(intent: string): string {
  return intentColorMap[intent] || intentColorMap['UNKNOWN'];
}

export const IntentTag: React.FC<IntentTagProps> = ({ intent, onClick }) => {
  const color = getIntentColor(intent);
  const isClickable = !!onClick;

  const handleClick = useCallback(() => {
    if (onClick) {
      onClick();
    }
  }, [onClick]);

  return (
    <span
      onClick={isClickable ? handleClick : undefined}
      className={`
        inline-flex items-center
        text-xs font-medium
        px-2 py-0.5
        rounded-sm
        transition-opacity duration-150
        ${isClickable ? 'cursor-pointer hover:opacity-80' : 'cursor-default'}
      `}
      style={{
        backgroundColor: `${color}1A`, // ~10% opacity in hex
        color: color,
      }}
    >
      {intent}
    </span>
  );
};
