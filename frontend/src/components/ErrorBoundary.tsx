// FILE: src/components/ErrorBoundary.tsx
// Global error boundary — prevents black screen on render crash.

import React from 'react';

interface State {
  hasError: boolean;
  error: Error | null;
  componentStack: string | null;
}

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  State
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null, componentStack: null };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[DM:BOUNDARY] Render crash:', error.message);
    console.error('[DM:BOUNDARY] Stack:', info.componentStack);
    this.setState({ componentStack: info.componentStack || null });
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div style={{ padding: 40, color: '#f87171', background: '#1e1e2e', minHeight: '100vh' }}>
          <h2>⚠️ Render Error</h2>
          <p style={{ color: '#a0a0b0' }}>
            {this.state.error?.message || 'Unknown error'}
          </p>
          <details style={{ marginTop: 16, color: '#6b7280' }}>
            <summary>Stack trace</summary>
            <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>
              {this.state.componentStack}
            </pre>
          </details>
        </div>
      );
    }
    return this.props.children;
  }
}
