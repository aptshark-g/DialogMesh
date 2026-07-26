// FILE: src/hooks/useV6TaskWS.ts
// WebSocket listener for v6 ExecutionPipeline → TaskFlow real-time updates

import { useEffect, useRef, useCallback } from 'react';
import { useTaskStore } from '../stores/taskStore';

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/v6/ws`;

export function useV6TaskWS() {
  const wsRef = useRef<WebSocket | null>(null);
  const taskStore = useTaskStore();

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[v6 WS] Connected');
      ws.send(JSON.stringify({ type: 'subscribe', topic: 'execution' }));
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const { type, payload } = msg;

        switch (type) {
          case 'step_start':
            taskStore.onStepStart(
              payload.index, payload.tool || '', payload.action || ''
            );
            break;
          case 'step_complete':
            taskStore.onStepComplete(
              payload.index, payload.status, payload.duration_ms || 0
            );
            break;
          case 'step_progress':
            // Live output — could display in detail panel
            break;
          case 'execution_done':
            taskStore.onExecutionDone(payload.summary || '');
            break;
          case 'connected':
            console.log('[v6 WS] Subscribed to execution events');
            break;
        }
      } catch (e) {
        console.warn('[v6 WS] Parse error:', e);
      }
    };

    ws.onclose = () => {
      console.log('[v6 WS] Disconnected, reconnecting in 3s...');
      wsRef.current = null;
      setTimeout(connect, 3000);
    };

    ws.onerror = (e) => {
      console.warn('[v6 WS] Error:', e);
    };
  }, [taskStore]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  return {
    connected: wsRef.current?.readyState === WebSocket.OPEN,
    reconnect: connect,
  };
}
