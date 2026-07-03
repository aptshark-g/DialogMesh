import React from 'react';
import { cn } from '@/lib/utils';

type BadgeVariant = 'default' | 'intent' | 'status';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  color?: string;
}

const intentColorMap: Record<string, { bg: string; text: string }> = {
  scanMemory: { bg: 'bg-[#D97706]/10', text: 'text-[#D97706]' },
  readMemory: { bg: 'bg-[#0D9488]/10', text: 'text-[#0D9488]' },
  writeMemory: { bg: 'bg-[#8B5CF6]/10', text: 'text-[#8B5CF6]' },
  hackValue: { bg: 'bg-[#E11D48]/10', text: 'text-[#E11D48]' },
  explain: { bg: 'bg-[#3B82F6]/10', text: 'text-[#3B82F6]' },
  provideCode: { bg: 'bg-[#10B981]/10', text: 'text-[#10B981]' },
  unknown: { bg: 'bg-[#6B6680]/10', text: 'text-[#6B6680]' },
};

const statusColorMap: Record<string, { bg: string; text: string }> = {
  success: { bg: 'bg-[#10B981]/10', text: 'text-[#10B981]' },
  warning: { bg: 'bg-[#F59E0B]/10', text: 'text-[#F59E0B]' },
  error: { bg: 'bg-[#EF4444]/10', text: 'text-[#EF4444]' },
  info: { bg: 'bg-[#3B82F6]/10', text: 'text-[#3B82F6]' },
};

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', color, children, ...props }, ref) => {
    let colorClasses = '';

    if (variant === 'intent' && color) {
      const mapped = intentColorMap[color] || intentColorMap.unknown;
      colorClasses = `${mapped.bg} ${mapped.text}`;
    } else if (variant === 'status' && color) {
      const mapped = statusColorMap[color] || statusColorMap.info;
      colorClasses = `${mapped.bg} ${mapped.text}`;
    } else {
      colorClasses = 'bg-[#1A1724] text-[#A9A5B8]';
    }

    return (
      <span
        ref={ref}
        className={cn(
          'inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-sm',
          colorClasses,
          className
        )}
        {...props}
      >
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';

export { Badge };
export type { BadgeProps };
