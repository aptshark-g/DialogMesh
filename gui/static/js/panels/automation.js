// panels/automation.js — 自动化工作流 + 自动逆向
(function() {
  'use strict';

  // ── Phase 7: Automated Reverse Engineering Pipeline (legacy) ──
  let autoReverseInterval = null;
  let autoReverseTaskId = null;

  async function startAutoReverse() {
    const strategy = document.getElementById('autoStrategy')?.value || 'general';
    const duration = parseInt(document.getElementById('autoDuration')?.value) || 30;
    const maxBP = parseInt(document.getElementById('autoMaxBP')?.value) || 4;
    const maxGP = parseInt(document.getElementById('autoMaxGP')?.value) || 8;

    const autoStatus = document.getElementById('autoStatus');
    const autoStartBtn = document.getElementById('autoStartBtn');
    if (autoStatus) autoStatus.innerHTML = '状态: <span style="color:#007bff">启动中...</span>';
    if (autoStartBtn) autoStartBtn.disabled = true;

    try {
      const r = await fetch(`${window.BASE || ''}/api/auto-reverse/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy, duration, max_breakpoints: maxBP, max_guard_pages: maxGP })
      });
      const j = await r.json();

      if (j.status === 'ok') {
        if (autoStatus) autoStatus.innerHTML = `状态: <span style="color:#28a745">采集中 (${duration}s)</span>`;
        const autoStopBtn = document.getElementById('autoStopBtn');
        if (autoStopBtn) autoStopBtn.disabled = false;

        const tbody = document.querySelector('#autoSelectedTable tbody');
        if (tbody) {
          tbody.innerHTML = '';
          (j.selected || []).forEach(a => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${a.address || 'N/A'}</td><td>${(a.confidence * 100).toFixed(0)}%</td><td>${a.suggested_type}</td><td>${a.reason}</td><td>${a.metadata?.breakpoint_type || 'unknown'}</td>`;
            tbody.appendChild(tr);
          });
        }
        autoReverseInterval = setInterval(() => pollAutoReverse(), 2000);
      } else {
        if (autoStatus) autoStatus.innerHTML = `状态: <span style="color:#dc3545">错误: ${j.message}</span>`;
        if (autoStartBtn) autoStartBtn.disabled = false;
      }
    } catch (e) {
      if (autoStatus) autoStatus.innerHTML = `状态: <span style="color:#dc3545">请求失败: ${e}</span>`;
      if (autoStartBtn) autoStartBtn.disabled = false;
    }
  }

  async function pollAutoReverse() {
    try {
      const r = await fetch(`${window.BASE || ''}/api/auto-reverse/status`);
      const j = await r.json();
      const statusEl = document.getElementById('autoStatus');
      if (!statusEl) return;
      if (j.stage === 'collecting') {
        const elapsed = j.elapsed || 0;
        statusEl.innerHTML = `状态: <span style="color:#007bff">采集中 (${elapsed.toFixed(1)}s / ${j.duration}s)</span><br>命中: ${j.hits_synced || 0} | 节点: ${j.nodes || 0} | 边: ${j.edges || 0}`;
      } else if (j.stage === 'completed') {
        clearInterval(autoReverseInterval); autoReverseInterval = null;
        statusEl.innerHTML = `状态: <span style="color:#28a745">已完成</span>`;
        const autoStopBtn = document.getElementById('autoStopBtn');
        const autoFinalizeBtn = document.getElementById('autoFinalizeBtn');
        const autoCopyBtn = document.getElementById('autoCopyBtn');
        const autoStartBtn = document.getElementById('autoStartBtn');
        if (autoStopBtn) autoStopBtn.disabled = true;
        if (autoFinalizeBtn) autoFinalizeBtn.disabled = false;
        if (autoCopyBtn) autoCopyBtn.disabled = false;
        if (autoStartBtn) autoStartBtn.disabled = false;
        if (j.ai_task) {
          const autoResult = document.getElementById('autoResult');
          if (autoResult) autoResult.textContent = `AI 分析任务已创建: ${j.ai_task.task_id}\nPrompt 文件: ${j.ai_task.prompt_file}\n\n请在终端运行: kimi\n然后粘贴 Prompt 文件内容。`;
          autoReverseTaskId = j.ai_task.task_id;
        }
      } else if (j.stage === 'failed') {
        clearInterval(autoReverseInterval); autoReverseInterval = null;
        statusEl.innerHTML = `状态: <span style="color:#dc3545">失败: ${j.error}</span>`;
        const autoStopBtn = document.getElementById('autoStopBtn');
        const autoStartBtn = document.getElementById('autoStartBtn');
        if (autoStopBtn) autoStopBtn.disabled = true;
        if (autoStartBtn) autoStartBtn.disabled = false;
      }
    } catch (e) {
      console.error('pollAutoReverse:', e);
    }
  }

  async function stopAutoReverse() {
    if (autoReverseInterval) { clearInterval(autoReverseInterval); autoReverseInterval = null; }
    try {
      const r = await fetch(`${window.BASE || ''}/api/auto-reverse/stop`, { method: 'POST' });
      const j = await r.json();
      const autoStatus = document.getElementById('autoStatus');
      const autoStopBtn = document.getElementById('autoStopBtn');
      const autoStartBtn = document.getElementById('autoStartBtn');
      if (autoStatus) autoStatus.innerHTML = `状态: <span style="color:#ffc107">已停止</span>`;
      if (autoStopBtn) autoStopBtn.disabled = true;
      if (autoStartBtn) autoStartBtn.disabled = false;
    } catch (e) {
      const autoStatus = document.getElementById('autoStatus');
      if (autoStatus) autoStatus.innerHTML = `状态: <span style="color:#dc3545">停止失败: ${e}</span>`;
    }
  }

  async function finalizeAutoReverse() {
    const autoStatus = document.getElementById('autoStatus');
    if (autoStatus) autoStatus.innerHTML = `状态: <span style="color:#007bff">生成报告中...</span>`;
    try {
      const r = await fetch(`${window.BASE || ''}/api/auto-reverse/finalize`, { method: 'POST' });
      const j = await r.json();
      if (j.status === 'ok') {
        if (autoStatus) autoStatus.innerHTML = `状态: <span style="color:#28a745">报告已生成</span>`;
        if (j.ai_task) {
          const autoResult = document.getElementById('autoResult');
          if (autoResult) autoResult.textContent = j.ai_task.prompt || 'Prompt 已生成。点击"复制 Kimi CLI Prompt"按钮。';
          autoReverseTaskId = j.ai_task.task_id;
          const autoCopyBtn = document.getElementById('autoCopyBtn');
          if (autoCopyBtn) autoCopyBtn.disabled = false;
        }
      } else {
        if (autoStatus) autoStatus.innerHTML = `状态: <span style="color:#dc3545">生成失败: ${j.message}</span>`;
      }
    } catch (e) {
      if (autoStatus) autoStatus.innerHTML = `状态: <span style="color:#dc3545">请求失败: ${e}</span>`;
    }
  }

  function copyAutoPrompt() {
    if (!autoReverseTaskId) { alert('没有可用的 Prompt'); return; }
    fetch(`${window.BASE || ''}/api/auto-reverse/prompt?task_id=${autoReverseTaskId}`)
      .then(r => r.json())
      .then(j => {
        if (j.prompt) {
          navigator.clipboard.writeText(j.prompt).then(() => {
            const autoCopyStatus = document.getElementById('autoCopyStatus');
            if (autoCopyStatus) autoCopyStatus.textContent = '已复制到剪贴板！';
            setTimeout(() => { if (autoCopyStatus) autoCopyStatus.textContent = ''; }, 3000);
          });
        } else { alert('无法获取 Prompt'); }
      });
  }

  // ── Phase 8: One-Click Workflow Engine (matches HTML wf* elements) ──
  let _wfPollTimer = null;
  let _wfIsRunning = false;

  async function startOneClickWorkflow() {
    if (!window.currentPid) {
      alert('请先附加进程');
      return;
    }
    const strategy = document.getElementById('wfStrategy')?.value || 'general';
    const duration = parseInt(document.getElementById('wfDuration')?.value) || 30;
    const maxBP = parseInt(document.getElementById('wfMaxBP')?.value) || 4;
    const maxGP = parseInt(document.getElementById('wfMaxGP')?.value) || 8;
    const autoRetry = document.getElementById('wfAutoRetry')?.checked ?? true;
    const maxRetries = parseInt(document.getElementById('wfMaxRetries')?.value) || 2;
    const aiProvider = document.getElementById('wfProvider')?.value || 'lmstudio';

    try {
      const r = await fetch('/api/workflow/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy, duration, max_breakpoints: maxBP, max_guard_pages: maxGP, auto_ai: true, ai_provider: aiProvider, auto_retry: autoRetry, max_retries: maxRetries }),
      });
      const j = await r.json();
      if (j.status === 'ok') {
        _wfIsRunning = true;
        updateControlButtons(true, false);
        const wfControlStatus = document.getElementById('wfControlStatus');
        if (wfControlStatus) { wfControlStatus.textContent = '工作流已启动...'; wfControlStatus.style.color = '#28a745'; }
        startPollWorkflowStatus();
      } else {
        alert('启动失败: ' + (j.message || JSON.stringify(j)));
      }
    } catch (e) {
      alert('请求失败: ' + e);
    }
  }

  function startPollWorkflowStatus() {
    if (_wfPollTimer) clearInterval(_wfPollTimer);
    _wfPollTimer = setInterval(pollWorkflowStatus, 1500);
    pollWorkflowStatus();
  }

  function stopPollWorkflowStatus() {
    if (_wfPollTimer) { clearInterval(_wfPollTimer); _wfPollTimer = null; }
  }

  async function pollWorkflowStatus() {
    try {
      const r = await fetch('/api/workflow/status');
      const s = await r.json();
      if (s.status === 'ok') {
        updateWorkflowUI(s);
        const state = s.state || 'idle';
        const done = state === 'completed' || state === 'failed' || state === 'cancelled';
        if (done && _wfIsRunning) {
          _wfIsRunning = false;
          stopPollWorkflowStatus();
          updateControlButtons(false, false);
          const wfControlStatus = document.getElementById('wfControlStatus');
          if (wfControlStatus) {
            if (state === 'completed') { wfControlStatus.textContent = '工作流已完成！'; wfControlStatus.style.color = '#28a745'; document.getElementById('wfReportBtn').disabled = false; }
            else if (state === 'failed') { wfControlStatus.textContent = '工作流失败'; wfControlStatus.style.color = '#dc3545'; }
            else { wfControlStatus.textContent = '已取消'; wfControlStatus.style.color = '#999'; }
          }
        }
        if (state === 'paused') updateControlButtons(false, true);
      }
    } catch (e) {
      console.error('Workflow poll error:', e);
    }
  }

  function updateControlButtons(running, paused) {
    const wfStartBtn = document.getElementById('wfStartBtn');
    const wfPauseBtn = document.getElementById('wfPauseBtn');
    const wfResumeBtn = document.getElementById('wfResumeBtn');
    const wfCancelBtn = document.getElementById('wfCancelBtn');
    if (wfStartBtn) wfStartBtn.disabled = running;
    if (wfPauseBtn) wfPauseBtn.disabled = !running || paused;
    if (wfResumeBtn) wfResumeBtn.disabled = !paused;
    if (wfCancelBtn) wfCancelBtn.disabled = !running && !paused;
  }

  function updateWorkflowUI(s) {
    const state = s.state || 'idle';
    const wfStateText = document.getElementById('wfStateText');
    const badge = document.getElementById('wfStateBadge');
    if (wfStateText) wfStateText.textContent = state;
    if (badge) {
      const colors = { idle: '#999', configured: '#6c757d', selecting_addresses: '#007bff', breakpoints_set: '#17a2b8', collecting: '#ffc107', paused: '#fd7e14', dfg_built: '#6f42c1', ai_analyzing: '#e83e8c', completed: '#28a745', failed: '#dc3545', cancelled: '#999' };
      badge.style.background = colors[state] || '#999';
      badge.textContent = state === 'idle' ? '空闲' : state === 'configured' ? '已配置' : state === 'selecting_addresses' ? '选择地址' : state === 'breakpoints_set' ? '断点就绪' : state === 'collecting' ? '采集中' : state === 'paused' ? '已暂停' : state === 'dfg_built' ? 'DFG 就绪' : state === 'ai_analyzing' ? 'AI 分析中' : state === 'completed' ? '已完成' : state === 'failed' ? '失败' : state === 'cancelled' ? '已取消' : state;
    }
    const totalSteps = s.total_steps || 7;
    const currentStep = s.current_step || 0;
    const pct = totalSteps > 0 ? Math.round((currentStep / totalSteps) * 100) : 0;
    const wfProgressBar = document.getElementById('wfProgressBar');
    const wfProgressText = document.getElementById('wfProgressText');
    const wfCurrentStep = document.getElementById('wfCurrentStep');
    const wfTotalSteps = document.getElementById('wfTotalSteps');
    if (wfProgressBar) wfProgressBar.style.width = pct + '%';
    if (wfProgressText) wfProgressText.textContent = pct + '% - ' + (s.step_name || '-');
    if (wfCurrentStep) wfCurrentStep.textContent = currentStep;
    if (wfTotalSteps) wfTotalSteps.textContent = totalSteps;

    for (let i = 0; i < totalSteps; i++) {
      const el = document.getElementById('wfStep-' + i);
      if (!el) continue;
      el.classList.remove('active', 'completed', 'error');
      if (i < currentStep) el.classList.add('completed');
      else if (i === currentStep) el.classList.add('active');
    }
    if (state === 'failed' || state === 'cancelled') {
      const el = document.getElementById('wfStep-' + currentStep);
      if (el) el.classList.add('error');
    }

    const wfSelectedCount = document.getElementById('wfSelectedCount');
    const wfHitsCount = document.getElementById('wfHitsCount');
    const wfDfgNodes = document.getElementById('wfDfgNodes');
    const wfDfgEdges = document.getElementById('wfDfgEdges');
    const wfRetryCount = document.getElementById('wfRetryCount');
    const dfg = s.dfg_stats || {};
    if (wfSelectedCount) wfSelectedCount.textContent = s.selected_count || 0;
    if (wfHitsCount) wfHitsCount.textContent = s.hits_count || 0;
    if (wfDfgNodes) wfDfgNodes.textContent = dfg.nodes || 0;
    if (wfDfgEdges) wfDfgEdges.textContent = dfg.edges || 0;
    if (wfRetryCount) wfRetryCount.textContent = s.retry_count || 0;

    // Show polling mode indicator (concise badge, replaces text — no accumulation)
    if (s.polling_mode) {
      const wfStateBadge = document.getElementById('wfStateBadge');
      if (wfStateBadge && !wfStateBadge.textContent.includes('[轮询]')) {
        wfStateBadge.textContent = (wfStateBadge.textContent || '') + ' [轮询]';
        wfStateBadge.style.background = '#fd7e14';
      }
      const wfControlStatus = document.getElementById('wfControlStatus');
      if (wfControlStatus && !wfControlStatus.textContent.includes('软件轮询')) {
        wfControlStatus.textContent = (wfControlStatus.textContent || '') + ' (软件轮询模式)';
        wfControlStatus.style.color = '#fd7e14';
      }
    }

    const errBox = document.getElementById('wfErrorBox');
    const warnBox = document.getElementById('wfWarningBox');
    if (warnBox) {
      // Only show warnings during breakpoints/collecting phase; clear afterwards
      const showWarnings = state === 'breakpoints_set' || state === 'collecting' || state === 'selecting_addresses';
      if (showWarnings && s.warnings && s.warnings.length > 0) {
        warnBox.style.display = 'block';
        warnBox.textContent = '提示: ' + s.warnings.join('; ');
      } else {
        warnBox.style.display = 'none';
      }
    }
    if (errBox) {
      if (s.errors && s.errors.length > 0) { errBox.style.display = 'block'; errBox.textContent = '错误: ' + s.errors.join('; '); }
      else { errBox.style.display = 'none'; }
    }

    const wfReportOutput = document.getElementById('wfReportOutput');
    if (s.report_preview && wfReportOutput) wfReportOutput.textContent = s.report_preview + '\n\n[报告已生成，点击"查看完整报告"获取全部内容]';
  }

  async function pauseWorkflow() {
    try {
      const r = await fetch('/api/workflow/pause', { method: 'POST' });
      const j = await r.json();
      if (j.status === 'ok') {
        updateControlButtons(false, true);
        const wfControlStatus = document.getElementById('wfControlStatus');
        if (wfControlStatus) { wfControlStatus.textContent = '已暂停'; wfControlStatus.style.color = '#fd7e14'; }
      } else { alert('暂停失败: ' + (j.message || '')); }
    } catch (e) { alert('请求失败: ' + e); }
  }

  async function resumeWorkflow() {
    try {
      const r = await fetch('/api/workflow/resume', { method: 'POST' });
      const j = await r.json();
      if (j.status === 'ok') {
        updateControlButtons(true, false);
        const wfControlStatus = document.getElementById('wfControlStatus');
        if (wfControlStatus) { wfControlStatus.textContent = '已恢复'; wfControlStatus.style.color = '#28a745'; }
      } else { alert('恢复失败: ' + (j.message || '')); }
    } catch (e) { alert('请求失败: ' + e); }
  }

  async function cancelWorkflow() {
    if (!confirm('确定要取消当前工作流吗？')) return;
    try {
      const r = await fetch('/api/workflow/cancel', { method: 'POST' });
      const j = await r.json();
      if (j.status === 'ok') {
        _wfIsRunning = false;
        stopPollWorkflowStatus();
        updateControlButtons(false, false);
        const wfControlStatus = document.getElementById('wfControlStatus');
        if (wfControlStatus) { wfControlStatus.textContent = '已取消'; wfControlStatus.style.color = '#999'; }
      } else { alert('取消失败: ' + (j.message || '')); }
    } catch (e) { alert('请求失败: ' + e); }
  }

  async function generateWorkflowReport() {
    try {
      const r = await fetch('/api/workflow/report');
      const j = await r.json();
      if (j.status === 'ok' && j.report) {
        const wfReportOutput = document.getElementById('wfReportOutput');
        const wfReportStatus = document.getElementById('wfReportStatus');
        if (wfReportOutput) wfReportOutput.textContent = j.report;
        if (wfReportStatus) wfReportStatus.textContent = '报告已加载';
      } else { alert('报告尚未就绪: ' + (j.message || '')); }
    } catch (e) { alert('请求失败: ' + e); }
  }

  function initAutomationPanel() {
    // No extra binding needed; uses inline onclick handlers
  }

  window.AutomationPanel = {
    init: initAutomationPanel,
    // Phase 7 (legacy auto-reverse)
    startAutoReverse: startAutoReverse,
    pollAutoReverse: pollAutoReverse,
    stopAutoReverse: stopAutoReverse,
    finalizeAutoReverse: finalizeAutoReverse,
    copyAutoPrompt: copyAutoPrompt,
    // Phase 8 (workflow — matches HTML)
    startOneClickWorkflow: startOneClickWorkflow,
    pauseWorkflow: pauseWorkflow,
    resumeWorkflow: resumeWorkflow,
    cancelWorkflow: cancelWorkflow,
    generateWorkflowReport: generateWorkflowReport,
  };
})();
