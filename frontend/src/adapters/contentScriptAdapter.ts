export interface PageContext {
  url: string;
  title: string;
  selectedText: string;
  metaDescription: string;
  timestamp: number;
}

export type ContentScriptMessageType =
  | 'DIALOGMESH_CONTEXT'
  | 'DIALOGMESH_REQUEST'
  | 'DIALOGMESH_RESPONSE'
  | 'DIALOGMESH_PING'
  | 'DIALOGMESH_READY';

export interface ContentScriptMessage {
  type: ContentScriptMessageType;
  payload: unknown;
  id: string;
  timestamp: number;
}

export type ContentScriptEventHandler = (payload: unknown) => void;

/**
 * ContentScriptAdapter bridges DialogMesh with external page contexts.
 * It uses window.postMessage for cross-origin/iframe communication,
 * simulating the browser extension content-script pattern.
 */
export class ContentScriptAdapter {
  private targetOrigin: string;
  private listeners: Map<ContentScriptMessageType, Set<ContentScriptEventHandler>>;
  private isActive: boolean;

  constructor(targetOrigin: string = '*') {
    this.targetOrigin = targetOrigin;
    this.listeners = new Map();
    this.isActive = false;
  }

  activate(): void {
    if (this.isActive) return;
    this.isActive = true;
    window.addEventListener('message', this.handleMessage);
  }

  deactivate(): void {
    this.isActive = false;
    window.removeEventListener('message', this.handleMessage);
  }

  private handleMessage = (event: MessageEvent): void => {
    if (event.source === window) return;
    const msg = event.data as ContentScriptMessage;
    if (!msg || typeof msg !== 'object') return;
    if (!msg.type?.startsWith('DIALOGMESH_')) return;

    const handlers = this.listeners.get(msg.type);
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(msg.payload);
        } catch (err) {
          console.error('[ContentScriptAdapter] Handler error:', err);
        }
      });
    }
  };

  on(type: ContentScriptMessageType, handler: ContentScriptEventHandler): () => void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)!.add(handler);
    return () => {
      this.listeners.get(type)?.delete(handler);
    };
  }

  post(type: ContentScriptMessageType, payload: unknown): void {
    const msg: ContentScriptMessage = {
      type,
      payload,
      id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      timestamp: Date.now(),
    };
    window.parent.postMessage(msg, this.targetOrigin);
  }

  extractPageContext(): PageContext {
    const meta = document.querySelector('meta[name="description"]');
    const selection = window.getSelection()?.toString() ?? '';
    return {
      url: window.location.href,
      title: document.title,
      selectedText: selection.slice(0, 2000),
      metaDescription: meta?.getAttribute('content') ?? '',
      timestamp: Date.now(),
    };
  }

  injectContext(): void {
    const ctx = this.extractPageContext();
    this.post('DIALOGMESH_CONTEXT', ctx);
  }

  get connected(): boolean {
    return this.isActive;
  }

  get origin(): string {
    return this.targetOrigin;
  }
}

export const defaultAdapter = new ContentScriptAdapter();
