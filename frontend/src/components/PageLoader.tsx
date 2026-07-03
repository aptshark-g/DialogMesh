import { Loader2 } from 'lucide-react';

export function PageLoader() {
  return (
    <div className="h-full w-full flex items-center justify-center bg-surface">
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <span className="text-sm text-text-secondary">加载中...</span>
      </div>
    </div>
  );
}
