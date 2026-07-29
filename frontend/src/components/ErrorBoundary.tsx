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
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', height: '100vh', fontFamily: 'system-ui',
          background: '#1a1a2e', color: '#e0e0e0', padding: '2rem',
        }}>
          <h1 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>⚠️ DialogMesh 加载错误</h1>
          <pre style={{
            background: '#16213e', padding: '1rem', borderRadius: '8px',
            maxWidth: '600px', overflow: 'auto', fontSize: '0.85rem',
            color: '#ff6b6b', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
          }}>
            {this.state.error?.message || 'Unknown error'}
            {'\n\n'}
            {this.state.componentStack || ''}
          </pre>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: '1rem', padding: '0.5rem 1.5rem',
              background: '#6366f1', color: 'white', border: 'none',
              borderRadius: '6px', cursor: 'pointer', fontSize: '1rem',
            }}
          >
            刷新页面
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
