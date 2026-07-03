// DialogMesh Extension Background Service Worker

interface ExtensionState {
  version: string;
  sidePanelOpen: boolean;
  connected: boolean;
  portCount: number;
}

const EXTENSION_STATE: ExtensionState = {
  version: '3.0.0',
  sidePanelOpen: false,
  connected: false,
  portCount: 0,
};

function log(level: 'info' | 'warn' | 'error', message: string, ...args: unknown[]) {
  const prefix = '[DialogMesh Background]';
  if (level === 'warn') {
    console.warn(prefix, message, ...args);
  } else if (level === 'error') {
    console.error(prefix, message, ...args);
  } else {
    console.log(prefix, message, ...args);
  }
}

function initialize() {
  log('info', 'Service worker initialized');

  if (chrome.sidePanel) {
    chrome.sidePanel
      .setPanelBehavior({ openPanelOnActionClick: true })
      .then(() => log('info', 'SidePanel behavior set'))
      .catch((err: unknown) => log('warn', 'SidePanel setup failed:', err));
  }
}

// 监听安装/更新
chrome.runtime.onInstalled.addListener((details) => {
  log('info', 'Extension installed/updated', details.reason);
  initialize();
});

// 监听浏览器启动
chrome.runtime.onStartup.addListener(() => {
  log('info', 'Browser startup');
  initialize();
});

// 消息通信
chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  const { type, payload } = request as { type: string; payload?: unknown };

  if (type === 'PING') {
    sendResponse({ type: 'PONG', timestamp: Date.now() });
    return true;
  }

  if (type === 'GET_STATE') {
    sendResponse({ state: { ...EXTENSION_STATE } });
    return true;
  }

  if (type === 'SET_STATE') {
    if (payload && typeof payload === 'object') {
      Object.assign(EXTENSION_STATE, payload);
    }
    sendResponse({ success: true });
    return true;
  }

  if (type === 'OPEN_SIDEPANEL') {
    if (chrome.sidePanel) {
      chrome.sidePanel
        .setPanelBehavior({ openPanelOnActionClick: true })
        .then(() => sendResponse({ success: true }))
        .catch(() => sendResponse({ success: false }));
      return true;
    }
    sendResponse({ success: false, error: 'sidePanel not available' });
    return true;
  }

  return false;
});

// 端口连接（长连接）
chrome.runtime.onConnect.addListener((port) => {
  EXTENSION_STATE.portCount++;
  EXTENSION_STATE.connected = EXTENSION_STATE.portCount > 0;
  log('info', 'Port connected:', port.name, 'total:', EXTENSION_STATE.portCount);

  port.onMessage.addListener((msg) => {
    const message = msg as { type?: string };
    if (message.type === 'HEARTBEAT') {
      port.postMessage({ type: 'HEARTBEAT_ACK', timestamp: Date.now() });
    } else if (message.type === 'GET_STATE') {
      port.postMessage({ type: 'STATE', state: { ...EXTENSION_STATE } });
    }
  });

  port.onDisconnect.addListener(() => {
    EXTENSION_STATE.portCount = Math.max(0, EXTENSION_STATE.portCount - 1);
    EXTENSION_STATE.connected = EXTENSION_STATE.portCount > 0;
    log('info', 'Port disconnected, remaining:', EXTENSION_STATE.portCount);
  });
});
