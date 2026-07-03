declare namespace chrome {
  namespace runtime {
    interface InstalledDetails {
      reason: 'install' | 'update' | 'chrome_update' | 'shared_module_update';
      previousVersion?: string;
      id?: string;
    }
    interface Port {
      name: string;
      postMessage(message: unknown): void;
      onMessage: {
        addListener(callback: (message: unknown) => void): void;
        removeListener(callback: (message: unknown) => void): void;
      };
      onDisconnect: {
        addListener(callback: () => void): void;
        removeListener(callback: () => void): void;
      };
    }
    interface OnInstalledEvent {
      addListener(callback: (details: InstalledDetails) => void): void;
      removeListener(callback: (details: InstalledDetails) => void): void;
    }
    interface OnStartupEvent {
      addListener(callback: () => void): void;
      removeListener(callback: () => void): void;
    }
    interface OnMessageEvent {
      addListener(
        callback: (
          request: unknown,
          sender: { tab?: { id?: number; url?: string } },
          sendResponse: (response: unknown) => void
        ) => boolean | void
      ): void;
      removeListener(
        callback: (
          request: unknown,
          sender: unknown,
          sendResponse: (response: unknown) => void
        ) => boolean | void
      ): void;
    }
    interface OnConnectEvent {
      addListener(callback: (port: Port) => void): void;
      removeListener(callback: (port: Port) => void): void;
    }
    const onInstalled: OnInstalledEvent;
    const onStartup: OnStartupEvent;
    const onMessage: OnMessageEvent;
    const onConnect: OnConnectEvent;
    const id: string | undefined;
  }
  namespace sidePanel {
    interface PanelBehavior {
      openPanelOnActionClick: boolean;
    }
    function setPanelBehavior(behavior: PanelBehavior): Promise<void>;
  }
  namespace action {
    interface Tab {
      id?: number;
      url?: string;
      title?: string;
      windowId?: number;
    }
    interface OnClickedEvent {
      addListener(callback: (tab: Tab) => void): void;
      removeListener(callback: (tab: Tab) => void): void;
    }
    const onClicked: OnClickedEvent;
  }
  namespace storage {
    interface StorageArea {
      get(keys?: string | string[] | Record<string, unknown> | null): Promise<Record<string, unknown>>;
      set(items: Record<string, unknown>): Promise<void>;
      remove(keys: string | string[]): Promise<void>;
    }
    const local: StorageArea;
    const sync: StorageArea;
    const session: StorageArea;
  }
}
