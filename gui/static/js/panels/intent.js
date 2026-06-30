// panels/intent.js — IntentAgent Interactive Panel
(function() {
  'use strict';

  let _intentPollTimer = null;
  let _intentRunning = false;
  let _lastSeenTime = 0;
  let _pendingRequiresResponse = false;
  let _messageIdCounter = 0;

  // ──────────────────────────────────────────────────────────────
  // UI Helpers
  // ──────────────────────────────────────────────────────────────

  function toggleIntentPanel() {
    const panel = document.getElementById('intentPanel');
    const app = document.getElementById('appContainer');
    const icon = document.getElementById('intentToggleIcon');
    if (!panel || !app) return;

    const isCollapsed = panel.classList.contains('collapsed');
    if (isCollapsed) {
      panel.classList.remove('collapsed');
      app.classList.remove('intent-closed');
      app.classList.add('intent-open');
      icon.textContent = '▶';
    } else {
      panel.classList.add('collapsed');
      app.classList.remove('intent-open');
      app.classList.add('intent-closed');
      icon.textContent = '◀';
    }
  }

  function _intentMsgId() {
    return 'msg_' + (++_messageIdCounter);
  }

  function addMessage(type, title, content, options) {
    const container = document.getElementById('intentMessages') || document.getElementById('intentChat');
    if (!container) return;

    const msg = document.createElement('div');
    msg.className = 'intent-msg ' + type;
    msg.id = _intentMsgId();

    let html = '';
    if (title && type === 'ai') {
      html += '<div class="msg-title">' + escapeHtml(title) + '</div>';
    }
    if (content) {
      html += '<div class="msg-content">' + formatMarkdown(content) + '</div>';
    }
    if (options && options.length > 0) {
      html += '<div class="msg-options" style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;">';
      options.forEach((opt, idx) => {
        html += '<button class="intent-option-btn" onclick="selectIntentOption(' + idx + ', this)" data-index="' + idx + '">' + escapeHtml(opt) + '</button>';
      });
      html += '</div>';
    }

    msg.innerHTML = html;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
    return msg.id;
  }

  function formatMarkdown(text) {
    // Very simple markdown for display, but preserves <details> HTML tags
    if (!text) return '';

    // Preserve details/summary tags before escaping
    const placeholders = [];
    function stash(tag) {
      placeholders.push(tag);
      return '\x00' + (placeholders.length - 1) + '\x00';
    }

    text = text.replace(/<details>/gi, () => stash('<details>'));
    text = text.replace(/<\/details>/gi, () => stash('</details>'));
    text = text.replace(/<summary>(.*?)<\/summary>/gi, (_, inner) => stash('<summary>' + escapeHtml(inner) + '</summary>'));

    text = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/```([\s\S]*?)```/g, '<pre>$1</pre>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');

    // Restore placeholders
    for (let i = 0; i < placeholders.length; i++) {
      text = text.replace('\x00' + i + '\x00', placeholders[i]);
    }
    return text;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function setIntentStatus(text, cssClass) {
    const el = document.getElementById('intentStatus');
    if (!el) return;
    el.textContent = text;
    el.className = 'intent-status' + (cssClass ? ' ' + cssClass : '');
  }

  function setInputEnabled(enabled) {
    const input = document.getElementById('intentInput');
    const sendBtn = document.getElementById('intentSendBtn');
    if (input) input.disabled = !enabled;
    if (sendBtn) sendBtn.disabled = !enabled;
    if (input && enabled) input.focus();
  }

  function clearOptions() {
    const opts = document.getElementById('intentOptions');
    if (opts) opts.innerHTML = '';
  }

  function addOptionButtons(options) {
    const opts = document.getElementById('intentOptions');
    if (!opts || !options || options.length === 0) return;
    opts.innerHTML = '';
    options.forEach((text, idx) => {
      const btn = document.createElement('button');
      btn.className = 'intent-option-btn';
      btn.textContent = text;
      btn.onclick = () => selectIntentOption(idx, btn);
      opts.appendChild(btn);
    });
  }

  // ──────────────────────────────────────────────────────────────
  // Session Control
  // ──────────────────────────────────────────────────────────────

  async function startIntentSession() {
    if (!window.attached) {
      alert('请先附加一个进程');
      return;
    }

    // Get provider and autonomy selections
    const providerEl = document.getElementById('intentProvider');
    const provider = providerEl ? providerEl.value : 'lmstudio';
    const autonomyEl = document.getElementById('intentAutonomy') || document.getElementById('intentMode');
    const autonomy = autonomyEl ? autonomyEl.value : 'interactive';

    // Clear previous messages
    const container = document.getElementById('intentMessages') || document.getElementById('intentChat');
    if (container) container.innerHTML = '';
    clearOptions();
    _lastSeenTime = 0;

    setIntentStatus('分析中...', 'running');
    addMessage('system', '', '正在启动 AI 会话... (' + (autonomy === 'full_auto' ? '全自动' : autonomy === 'semi_auto' ? '半自动' : '交互') + ')');

    const startBtn = document.getElementById('intentStartBtn');
    const stopBtn = document.getElementById('intentStopBtn');
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = false;

    try {
      const r = await fetch((window.BASE || '') + '/api/intent/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: provider, autonomy: autonomy })
      });
      const j = await r.json();
      if (j.status === 'ok') {
        _intentRunning = true;
        if (!_intentPollTimer) {
          _intentPollTimer = setInterval(pollIntentStatus, 1200);
        }
        // Auto-expand panel on start
        const panel = document.getElementById('intentPanel');
        if (panel && panel.classList.contains('collapsed')) {
          toggleIntentPanel();
        }
      } else {
        addMessage('error', '', '启动失败: ' + (j.message || ''));
        setIntentStatus('空闲');
        const startBtn2 = document.getElementById('intentStartBtn');
        const stopBtn2 = document.getElementById('intentStopBtn');
        if (startBtn2) startBtn2.disabled = false;
        if (stopBtn2) stopBtn2.disabled = true;
      }
    } catch (e) {
      addMessage('error', '', '请求失败: ' + e);
      setIntentStatus('空闲');
      document.getElementById('intentStartBtn').disabled = false;
      document.getElementById('intentStopBtn').disabled = true;
    }
  }

  async function stopIntentSession() {
    try {
      await fetch((window.BASE || '') + '/api/intent/cancel', { method: 'POST' });
    } catch (e) {}
    _intentRunning = false;
    if (_intentPollTimer) {
      clearInterval(_intentPollTimer);
      _intentPollTimer = null;
    }
    setIntentStatus('空闲');
    const startBtn = document.getElementById('intentStartBtn');
    const stopBtn = document.getElementById('intentStopBtn');
    if (startBtn) startBtn.disabled = false;
    if (stopBtn) stopBtn.disabled = true;
    setInputEnabled(false);
    clearOptions();
    addMessage('system', '', '会话已停止');
  }

  // ──────────────────────────────────────────────────────────────
  // Polling
  // ──────────────────────────────────────────────────────────────

  async function pollIntentStatus() {
    if (!_intentRunning) return;

    try {
      const url = (window.BASE || '') + '/api/intent/status?last_seen=' + _lastSeenTime;
      const r = await fetch(url);
      const j = await r.json();
      if (j.status !== 'ok') return;

      // Update state display
      if (j.state) {
        const stateMap = {
          'idle': '空闲',
          'analyzing_process': '分析进程...',
          'waiting_user': '等待用户',
          'running_tool': '执行工具...',
          'thinking': '处理中...',
          'done': '完成',
          'error': '错误',
        };
        const stateText = stateMap[j.state] || j.state;
        const cssClass = j.state === 'running_tool' ? 'running' : (j.state === 'waiting_user' ? 'waiting' : '');
        setIntentStatus(stateText, cssClass);
      }

      // Process new messages
      if (j.new_messages && j.new_messages.length > 0) {
        for (const msg of j.new_messages) {
          _lastSeenTime = Math.max(_lastSeenTime, msg.timestamp || Date.now() / 1000);
          renderIntentMessage(msg);
        }
      }

      // Update right sidebar
      updateSidebar(j);

      // Handle pending question state
      if (j.has_pending_question) {
        setInputEnabled(true);
      } else if (j.state === 'done' || j.state === 'error') {
        setInputEnabled(false);
        _intentRunning = false;
        if (_intentPollTimer) {
          clearInterval(_intentPollTimer);
          _intentPollTimer = null;
        }
        const startBtn2 = document.getElementById('intentStartBtn');
        const stopBtn2 = document.getElementById('intentStopBtn');
        if (startBtn2) startBtn2.disabled = false;
        if (stopBtn2) stopBtn2.disabled = true;
      }

    } catch (e) {
      console.error('[Intent] poll error:', e);
    }
  }

  function updateSidebar(data) {
    const taskEl = document.getElementById('intentCurrentTask');
    const toolsEl = document.getElementById('intentToolCalls');
    const statusEl = document.getElementById('intentPanelStatus');

    if (statusEl) {
      const stateMap = {
        'idle': '空闲',
        'analyzing_process': '分析进程...',
        'waiting_user': '等待用户',
        'running_tool': '执行工具...',
        'thinking': '处理中...',
        'done': '完成',
        'error': '错误',
      };
      statusEl.textContent = stateMap[data.state] || data.state || '就绪';
    }

    if (taskEl && data.current_task) {
      taskEl.textContent = data.current_task;
    } else if (taskEl && data.new_messages && data.new_messages.length > 0) {
      const last = data.new_messages[data.new_messages.length - 1];
      if (last.type === 'ai') taskEl.textContent = last.content.substring(0, 100) + '...';
    }

    if (toolsEl && data.tool_calls) {
      toolsEl.textContent = data.tool_calls.map(t => t.tool_name || t.name).join(', ');
    } else if (toolsEl && data.state === 'running_tool') {
      toolsEl.textContent = '执行中...';
    } else if (toolsEl) {
      toolsEl.textContent = '无工具调用';
    }
  }

  function renderIntentMessage(msg) {
    const type = msg.type || 'ai';
    const title = msg.title || '';
    const content = msg.content || '';
    const options = msg.options || [];
    const requiresResponse = msg.requires_response || false;

    // Map message types to CSS classes
    let cssClass = 'ai';
    if (type === 'error') cssClass = 'error';
    else if (type === 'finding') cssClass = 'finding';
    else if (type === 'progress') cssClass = 'system';

    const msgId = addMessage(cssClass, title, content, requiresResponse ? options : []);

    // If options provided, show them
    if (requiresResponse && options && options.length > 0) {
      addOptionButtons(options);
      _pendingRequiresResponse = true;
    } else if (requiresResponse) {
      setInputEnabled(true);
      _pendingRequiresResponse = true;
    } else {
      clearOptions();
    }
  }

  async function sendIntentTask() {
    const input = document.getElementById('intentInput');
    const text = input ? input.value.trim() : '';
    if (!text) { alert('请输入任务描述'); return; }

    // Start session if not running
    if (!_intentRunning) {
      await startIntentSession();
    }
    // Send the task text
    await sendIntentResponse(text);
  }

  // ──────────────────────────────────────────────────────────────
  // User Response
  // ──────────────────────────────────────────────────────────────

  async function sendIntentResponse(text, selectedOption) {
    const input = document.getElementById('intentInput');
    const responseText = text !== undefined ? text : (input ? input.value.trim() : '');
    if (!responseText && selectedOption === undefined) return;

    // Add user message to UI
    if (responseText) {
      addMessage('user', '', responseText);
    } else if (selectedOption !== undefined) {
      const opts = document.getElementById('intentOptions');
      if (opts && opts.children[selectedOption]) {
        addMessage('user', '', opts.children[selectedOption].textContent);
      }
    }

    // Clear input
    if (input) input.value = '';
    clearOptions();
    setInputEnabled(false);

    try {
      const r = await fetch((window.BASE || '') + '/api/intent/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: responseText || '',
          selected_option: selectedOption,
        })
      });
      const j = await r.json();
      if (j.status !== 'ok') {
        addMessage('error', '', '发送失败: ' + (j.message || ''));
      }
      // Immediate poll for faster response
      setTimeout(pollIntentStatus, 300);
    } catch (e) {
      addMessage('error', '', '发送失败: ' + e);
      setInputEnabled(true);
    }
  }

  function selectIntentOption(index, btnElement) {
    // Mark selected visually
    if (btnElement) {
      const parent = btnElement.parentElement;
      if (parent) {
        Array.from(parent.children).forEach(c => c.classList.remove('selected'));
      }
      btnElement.classList.add('selected');
    }
    sendIntentResponse('', index);
  }

  // ──────────────────────────────────────────────────────────────
  // Draggable Width Resizer
  // ──────────────────────────────────────────────────────────────

  const INTENT_MIN_WIDTH = 280;
  const INTENT_MAX_WIDTH = 700;
  const INTENT_STORAGE_KEY = 'intentPanelWidth';

  function initResizer() {
    const panel = document.getElementById('intentPanel');
    const resizer = document.getElementById('intentResizer');
    if (!panel || !resizer) return;

    // Restore saved width from localStorage
    const saved = localStorage.getItem(INTENT_STORAGE_KEY);
    if (saved) {
      const w = parseInt(saved, 10);
      if (w >= INTENT_MIN_WIDTH && w <= INTENT_MAX_WIDTH) {
        setPanelWidth(w);
      }
    }

    let isDragging = false;
    let startX = 0;
    let startWidth = 0;

    resizer.addEventListener('mousedown', function(e) {
      if (panel.classList.contains('collapsed')) return;
      isDragging = true;
      startX = e.clientX;
      startWidth = panel.getBoundingClientRect().width;
      resizer.classList.add('dragging');
      panel.style.transition = 'none';
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', function(e) {
      if (!isDragging) return;
      const delta = startX - e.clientX; // dragging left → wider panel
      let newWidth = startWidth + delta;
      newWidth = Math.max(INTENT_MIN_WIDTH, Math.min(INTENT_MAX_WIDTH, newWidth));
      setPanelWidth(newWidth);
    });

    document.addEventListener('mouseup', function() {
      if (!isDragging) return;
      isDragging = false;
      resizer.classList.remove('dragging');
      panel.style.transition = '';
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      // Save to localStorage
      const w = panel.getBoundingClientRect().width;
      localStorage.setItem(INTENT_STORAGE_KEY, String(w));
    });
  }

  function setPanelWidth(px) {
    document.documentElement.style.setProperty('--intent-panel-width', px + 'px');
  }

  // Initialize resizer on DOM ready
  function initIntentPanel() {
    // Intent panel initializes itself via DOMContentLoaded (initResizer)
    // This function is a no-op for app.js compatibility
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initResizer);
  } else {
    initResizer();
  }

  // ──────────────────────────────────────────────────────────────
  // Expose to global scope
  // ──────────────────────────────────────────────────────────────

  window.toggleIntentPanel = toggleIntentPanel;
  window.sendIntentTask = sendIntentTask;
  window.startIntentSession = startIntentSession;
  window.stopIntentSession = stopIntentSession;
  window.sendIntentResponse = sendIntentResponse;
  window.selectIntentOption = selectIntentOption;

  window.IntentPanel = {
    init: initIntentPanel,
    toggle: toggleIntentPanel,
    start: startIntentSession,
    stop: stopIntentSession,
    send: sendIntentResponse,
    select: selectIntentOption,
    sendTask: sendIntentTask,
  };

})();
