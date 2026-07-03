import { useEffect, useRef, useCallback } from 'react';
import {
  ContentScriptAdapter,
  type PageContext,
  type ContentScriptMessageType,
} from '../adapters/contentScriptAdapter';

export interface UseContentScriptOptions {
  onContext?: (ctx: PageContext) => void;
  onRequest?: (payload: unknown) => void;
  onResponse?: (payload: unknown) => void;
  targetOrigin?: string;
}

export function useContentScript(options: UseContentScriptOptions = {}) {
  const { onContext, onRequest, onResponse, targetOrigin = '*' } = options;
  const adapterRef = useRef<ContentScriptAdapter | null>(null);

  useEffect(() => {
    const adapter = new ContentScriptAdapter(targetOrigin);
    adapterRef.current = adapter;
    adapter.activate();

    const unsubscribers: (() => void)[] = [];

    if (onContext) {
      unsubscribers.push(
        adapter.on('DIALOGMESH_CONTEXT', (data) => onContext(data as PageContext))
      );
    }
    if (onRequest) {
      unsubscribers.push(adapter.on('DIALOGMESH_REQUEST', onRequest));
    }
    if (onResponse) {
      unsubscribers.push(adapter.on('DIALOGMESH_RESPONSE', onResponse));
    }

    return () => {
      unsubscribers.forEach((unsub) => unsub());
      adapter.deactivate();
    };
  }, [onContext, onRequest, onResponse, targetOrigin]);

  const injectContext = useCallback(() => {
    adapterRef.current?.injectContext();
  }, []);

  const sendMessage = useCallback((type: ContentScriptMessageType, payload: unknown) => {
    adapterRef.current?.post(type, payload);
  }, []);

  const ping = useCallback(() => {
    adapterRef.current?.post('DIALOGMESH_PING', { source: 'dialogmesh-app' });
  }, []);

  return {
    adapter: adapterRef.current,
    injectContext,
    sendMessage,
    ping,
    connected: adapterRef.current?.connected ?? false,
  };
}
