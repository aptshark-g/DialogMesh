import { useEffect } from 'react';
import { useContentScript } from '@/hooks/useContentScript';
import { useOverlayStore } from '@/stores/overlayStore';

/**
 * ContentScriptBridge initializes the cross-context adapter.
 * It does not render any DOM elements — it acts as a passive bridge
 * between DialogMesh and external page contexts (e.g. browser extension
 * content scripts or parent iframes).
 */
export function ContentScriptBridge() {
  const { open, incrementUnread } = useOverlayStore();

  const { injectContext } = useContentScript({
    onContext: (ctx) => {
      console.log('[DialogMesh] Page context received:', ctx);
      // Auto-open overlay when context is injected from a parent frame
      if (window.self !== window.top) {
        open();
      }
    },
    onResponse: () => {
      incrementUnread();
    },
  });

  useEffect(() => {
    // If running inside an iframe, broadcast readiness and inject context
    if (window.self !== window.top) {
      injectContext();
    }
  }, [injectContext]);

  return null;
}
