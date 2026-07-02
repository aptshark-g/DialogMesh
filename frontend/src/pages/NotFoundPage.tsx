import { Home } from 'lucide-react';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="h-full flex flex-col items-center justify-center max-w-5xl mx-auto text-center">
      <h1 className="text-6xl font-bold text-primary mb-4">404</h1>
      <p className="text-lg text-text-secondary mb-6">页面未找到</p>
      <Link
        to="/"
        className={[
          'px-4 py-2 rounded-lg bg-primary text-white',
          'text-sm font-medium hover:bg-primary-dark',
          'transition-colors flex items-center gap-2',
        ].join(' ')}
      >
        <Home className="w-4 h-4" />
        返回首页
      </Link>
    </div>
  );
}
