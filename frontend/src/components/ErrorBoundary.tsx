// FILE: src/components/ErrorBoundary.tsx

import { Component, type ReactNode } from 'react';

interface Props { children: ReactNode; fallback?: ReactNode }
interface State { hasError: boolean; error: string }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: '' };

  static getDerivedStateFromError(err: Error): State {
    return { hasError: true, error: err.message };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex flex-col items-center justify-center h-64 gap-4 p-8">
          <div className="text-4xl">⚠️</div>
          <h2 className="text-lg font-semibold text-text-primary">页面渲染错误</h2>
          <p className="text-sm text-text-muted max-w-md text-center">{this.state.error}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: '' })}
            className="px-4 py-2 rounded-lg bg-primary text-white text-sm hover:bg-primary-dark transition-colors"
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
