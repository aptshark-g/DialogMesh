// panels/agent.js
(function() {
  'use strict';

  let _agentPollTimer = null;
  let _agentIsRunning = false;

  function initAgentPanel() {
    // Agent panel uses inline onclick handlers; no additional JS event binding needed
  }

  async function startAgent() {
    const task = document.getElementById('agentTask').value.trim();
    if (!task) { alert('请输入任务描述'); return; }

    const hintStr = document.getElementById('agentHint').value.trim();
    let hint = {};
    if (hintStr) {
      try { hint = JSON.parse(hintStr); } catch (e) { alert('辅助信息格式错误，应为 JSON'); return; }
    }

    document.getElementById('agentLog').textContent = '';
    document.getElementById('agentConclusion').textContent = '任务运行中...';
    document.getElementById('agentCompressStats').textContent = '无运行数据';
    document.getElementById('agentConfirmPanel').style.display = 'none';

    updateAgentUI('running', 'Agent 运行中...');

    try {
      const r = await fetch(`${window.BASE || ''}/api/agent/start`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          task: task,
          hint: hint,
          max_steps: parseInt(document.getElementById('agentMaxSteps').value) || 15,
          provider: document.getElementById('agentProvider').value,
          confirm_write: document.getElementById('agentConfirmWrite').checked,
        })
      });
      const j = await r.json();
      if (j.status === 'ok') {
        _agentIsRunning = true;
        document.getElementById('agentStartBtn').disabled = true;
        document.getElementById('agentStopBtn').disabled = false;
        if (!_agentPollTimer) _agentPollTimer = setInterval(pollAgentStatus, 1500);
      } else {
        alert('启动失败: ' + (j.message || ''));
        updateAgentUI('idle', j.message || '启动失败');
      }
    } catch (e) {
      alert('请求失败: ' + e);
      updateAgentUI('idle', '请求失败');
    }
  }

  async function stopAgent() {
    try {
      await fetch(`${window.BASE || ''}/api/agent/stop`, { method: 'POST' });
    } catch (e) {}
    _agentIsRunning = false;
    document.getElementById('agentStartBtn').disabled = false;
    document.getElementById('agentStopBtn').disabled = true;
    if (_agentPollTimer) { clearInterval(_agentPollTimer); _agentPollTimer = null; }
    updateAgentUI('idle', '已停止');
  }

  async function agentConfirm(approved) {
    try {
      const r = await fetch(`${window.BASE || ''}/api/agent/confirm`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ approved: approved })
      });
      const j = await r.json();
      if (j.status === 'ok') {
        document.getElementById('agentConfirmPanel').style.display = 'none';
      }
    } catch (e) { alert('确认失败: ' + e); }
  }

  async function pollAgentStatus() {
    if (!_agentIsRunning) return;
    try {
      const r = await fetch(`${window.BASE || ''}/api/agent/status`);
      const s = await r.json();
      if (s.status !== 'ok') return;

      updateAgentUI(s.state, s.state === 'running' ? 'Agent 运行中...' : (s.message || s.state));

      if (s.steps && s.steps.length > 0) {
        let logText = '';
        for (const step of s.steps) {
          const time = new Date(step.timestamp * 1000).toLocaleTimeString();
          const icon = step.success ? '[OK]' : '[FAIL]';
          logText += `[${time}] Step ${step.step}: ${icon} ${step.action}\n`;
          logText += `  REASON: ${step.reason || 'N/A'}\n`;
          logText += `  PARAMS: ${JSON.stringify(step.params)}\n`;
          logText += `  RESULT: ${step.result}\n\n`;
        }
        const logEl = document.getElementById('agentLog');
        logEl.textContent = logText;
        logEl.scrollTop = logEl.scrollHeight;
      }

      if (s.conclusion && Object.keys(s.conclusion).length > 0) {
        document.getElementById('agentConclusion').textContent = JSON.stringify(s.conclusion, null, 2);
      }

      if (s.compression_stats && Object.keys(s.compression_stats).length > 0) {
        const cs = s.compression_stats;
        let statsText = `Total steps: ${cs.total_steps || 0}\n`;
        statsText += `Debloat savings: ${cs.debloat_savings || 0} tokens\n`;
        statsText += `Stage folds: ${cs.stage_folds || 0}\n`;
        statsText += `LLM compresses: ${cs.llm_compresses || 0} (${Math.round(cs.llm_compress_time || 0)}s)\n`;
        statsText += `Recent steps: ${cs.recent_steps || 0}\n`;
        document.getElementById('agentCompressStats').textContent = statsText;
      }

      if (s.confirm_request) {
        document.getElementById('agentConfirmPanel').style.display = 'block';
        document.getElementById('agentConfirmReason').textContent = s.confirm_request.reason || 'Agent 请求执行写操作';
        document.getElementById('agentConfirmDetails').textContent = `Action: ${s.confirm_request.action}\nParams: ${JSON.stringify(s.confirm_request.params, null, 2)}`;
      }

      if (s.state === 'completed' || s.state === 'failed' || s.state === 'cancelled') {
        _agentIsRunning = false;
        document.getElementById('agentStartBtn').disabled = false;
        document.getElementById('agentStopBtn').disabled = true;
        if (_agentPollTimer) { clearInterval(_agentPollTimer); _agentPollTimer = null; }
      }
    } catch (e) { console.error('Agent poll error:', e); }
  }

  function updateAgentUI(state, text) {
    const badge = document.getElementById('agentStatusBadge');
    const txt = document.getElementById('agentStatusText');
    const colors = {
      'idle': '#999', 'configured': '#6c757d', 'running': '#28a745',
      'paused': '#fd7e14', 'waiting_confirm': '#ffc107', 'completed': '#28a745',
      'failed': '#dc3545', 'cancelled': '#6c757d'
    };
    badge.style.background = colors[state] || '#999';
    badge.textContent = state;
    txt.textContent = text || '';
  }

  window.AgentPanel = {
    init: initAgentPanel,
    start: startAgent,
    stop: stopAgent,
    confirm: agentConfirm,
    poll: pollAgentStatus,
    updateUI: updateAgentUI,
  };
})();
