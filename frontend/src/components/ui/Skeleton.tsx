import React from 'react';
import { cn } from '@/lib/utils';

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  width?: string | number;
  height?: string | number;
  circle?: boolean;
}

const Skeleton: React.FC<SkeletonProps> = ({
  width = '100%',
  height = '16px',
  circle = false,
  className,
  style,
  ...props
}) => {
  const widthValue = typeof width === 'number' ? `${width}px` : width;
  const heightValue = typeof height === 'number' ? `${height}px` : height;

  return (
    <div
      className={cn(
        'skeleton bg-[#252134] relative overflow-hidden',
        circle && 'rounded-full',
        !circle && 'rounded-md',
        className
      )}
      style={{
        width: widthValue,
        height: circle ? widthValue : heightValue,
        ...style,
      }}
      {...props}
    />
  );
};

export { Skeleton };
export type { SkeletonProps };
