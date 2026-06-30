// gui/static/js/app.js — v2 应用框架（精简版，面板逻辑已拆分到 panels/*.js）
console.log('[app.js v2] MemoryGraph GUI initializing...');

// 全局状态（直接使用 window 属性供所有面板共享）
// 不再使用本地 let，全部通过 window.xxx 访问，确保面板间状态一致
window.attached = false;
window.currentPid = null;
window.scanResults = [];
window.filteredResults = [];
window.watchList = [];
window.trackList = [];
window.lastScanType = 2;
window.selectedAddress = '';
window.sortColumn = '';
window.sortDirection = 'asc';

// 面板配置
const PANELS = [
  {id: 'process', label: '进程', icon: '🔍', panel: 'ProcessPanel'},
  {id: 'memory', label: '内存', icon: '💾', panel: 'MemoryPanel'},
  {id: 'watch', label: '追踪', icon: '📊', panel: 'TrackingPanel'},
  {id: 'disasm', label: '反汇编', icon: '📋', panel: 'DisasmPanel'},
  {id: 'ai', label: 'AI助手', icon: '🤖', panel: 'AIPanel'},
  {id: 'automation', label: '自动化', icon: '⚙️', panel: 'AutomationPanel'},
  {id: 'workflow', label: '工作流', icon: '🔁', panel: 'AutomationPanel'},
  {id: 'intent', label: 'Agent', icon: '✨', panel: 'AgentPanel'},
];

const PANEL_ID_MAP = {process:'ce', memory:'memory', watch:'watch', disasm:'disasm', ai:'ai', automation:'automation', workflow:'workflow', intent:'intent'};
const TAB_MAP = {ce:'process', memory:'memory', watch:'watch', disasm:'disasm', pointer:'disasm', debugger:'disasm', dfg:'disasm', ai:'ai', automation:'automation', workflow:'workflow', intent:'intent'};
const _initSet = new Set();

function buildSidebar() {
  if (document.querySelector('.sidebar')) return;
  const sb = document.createElement('div');
  sb.className = 'sidebar';
  
  // Logo
  const logo = document.createElement('div');
  logo.className = 'sidebar-logo';
  logo.textContent = 'MemoryGraph';
  sb.appendChild(logo);
  
  PANELS.forEach(p => {
    const btn = document.createElement('button');
    btn.className = 'sidebar-item';
    btn.dataset.id = p.id;
    btn.innerHTML = `<span class="icon">${p.icon}</span> ${p.label}`;
    btn.onclick = () => switchPanel(p.id);
    sb.appendChild(btn);
  });
  document.body.insertBefore(sb, document.body.firstChild);
}

function switchPanel(id) {
  console.log('[switchPanel] id=' + id + ' mapped=' + (PANEL_ID_MAP[id] || id));
  document.querySelectorAll('.sidebar-item').forEach(el => el.classList.toggle('active', el.dataset.id === id));
  const oldId = PANEL_ID_MAP[id] || id;
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  const p = document.getElementById(oldId);
  if (p) {
    p.classList.add('active');
    console.log('[switchPanel] activated panel #' + oldId);
  } else {
    console.error('[switchPanel] panel not found: #' + oldId + ' (original id=' + id + ')');
  }
  // 旧标签按钮兼容
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  const tab = document.querySelector(`.tab[onclick="switchTab('${oldId}')"]`);
  if (tab) tab.classList.add('active');
  const cfg = PANELS.find(p => p.id === id);
  if (cfg && !_initSet.has(id)) {
    const panel = window[cfg.panel];
    if (panel && typeof panel.init === 'function') { panel.init(); _initSet.add(id); }
  }
}

function switchTab(id) { switchPanel(TAB_MAP[id] || id); }

async function updateGlobalStatus() {
  const data = await window.api.get('/api/status');
  if (!data) return;
  window.attached = data.attached;
  window.currentPid = data.pid;
  const gs = document.getElementById('globalStatus');
  const ap = document.getElementById('attachedPid');
  if (gs) gs.textContent = window.attached ? '已附加进程' : '未附加进程';
  if (ap) ap.textContent = window.attached ? `PID: ${window.currentPid}` : '';
  const btns = {regionsBtn: !window.attached, modifyBtn: !window.attached, addWatchBtn: !window.attached, addTrackBtn: !window.attached, startTrackBtn: !window.attached || window.trackList.length===0, taintBtn: !window.attached};
  Object.entries(btns).forEach(([k,v]) => { const el = document.getElementById(k); if (el) el.disabled = v; });
  const ab = document.getElementById('attachBtn');
  if (ab) { ab.textContent = window.attached ? '切换进程' : '附加进程'; ab.style.opacity = window.attached ? '0.8' : '1'; ab.disabled = false; }
  if (window.ProcessPanel) window.ProcessPanel.updateGlobalStatus();
}

function fillBaseAddr(inputId) {
  const el = document.getElementById(inputId);
  if (!el) return;
  if (!window.processBaseAddr) {
    alert('未获取进程基址，请先附加进程');
    return;
  }
  el.value = window.processBaseAddr;
}

// 兼容工具
function showStatus(id, text) { return window.Utils?.showStatus?.(id, text); }
function wildmatch(p, t) { return window.Utils?.wildmatch?.(p, t); }
function copyToClipboard(id) { return window.Utils?.copyToClipboard?.(id) || window.AIPanel?.copyPrompt?.(id); }

// 进程
function searchProcesses() {
  console.log('[app.searchProcesses] forwarding to ProcessPanel...');
  if (!window.ProcessPanel) {
    console.error('[app.searchProcesses] window.ProcessPanel not available');
    alert('ProcessPanel 未加载，请刷新页面 (Ctrl+Shift+R)');
    return;
  }
  return window.ProcessPanel.searchProcesses();
}
function showAllProcesses() {
  console.log('[app.showAllProcesses] forwarding to ProcessPanel...');
  if (!window.ProcessPanel) {
    console.error('[app.showAllProcesses] window.ProcessPanel not available');
    return;
  }
  return window.ProcessPanel.showAllProcesses();
}
function attachSelected() { return window.ProcessPanel?.attachSelected?.(); }
function launchTarget() { return window.ProcessPanel?.launchTarget?.(); }
function showMemoryRegions() { return window.ProcessPanel?.showMemoryRegions?.() || window.MemoryPanel?.showMemoryRegions?.(); }

// 内存扫描
function onScanModeChange() { return window.MemoryPanel?.onScanModeChange?.(); }
function firstScan() { return window.MemoryPanel?.firstScan?.(); }
function nextScan() { return window.MemoryPanel?.nextScan?.(); }
function filterResults() { return window.MemoryPanel?.filterResults?.(); }
function sortResults(col) { return window.MemoryPanel?.sortResults?.(col); }
function refreshResults() { return window.MemoryPanel?.refreshResults?.(); }
function modifySelected() { return window.MemoryPanel?.modifySelected?.(); }
function addToWatch() { return window.MemoryPanel?.addToWatch?.(); }
function addToTrack() { return window.MemoryPanel?.addToTrack?.() || window.TrackingPanel?.addToTrack?.(); }
function doPointerChainWrite() { return window.MemoryPanel?.doPointerChainWrite?.(); }
function doPointerChainResolve() { return window.MemoryPanel?.doPointerChainResolve?.(); }

// 监视
function updateWatchList() { return window.TrackingPanel?.updateWatchList?.(); }
function removeWatchItem() { return window.TrackingPanel?.removeWatchItem?.(); }

// Hex 视图
function refreshMemoryView() { return window.MemoryPanel?.refreshMemoryView?.(); }
function autoFollowFirstScan() { return window.MemoryPanel?.autoFollowFirstScan?.(); }
function trackSelectedMemory() { return window.MemoryPanel?.trackSelectedMemory?.() || window.TrackingPanel?.trackSelectedMemory?.(); }
function clearMemorySelection() { return window.MemoryPanel?.clearMemorySelection?.(); }

// 反汇编
function doDisasm() { return window.DisasmPanel?.doDisasm?.(); }
function gotoEIP() { return window.DisasmPanel?.gotoEIP?.(); }
function searchPattern() { return window.DisasmPanel?.searchPattern?.(); }
function setBreakpoint() { return window.DisasmPanel?.setBreakpoint?.(); }
function clearAllBp() { return window.DisasmPanel?.clearAllBp?.(); }
function refreshBpStatus() { return window.DisasmPanel?.refreshBpStatus?.(); }
function scanWrites() { return window.DisasmPanel?.scanWrites?.(); }
function tracePropagation() { return window.DisasmPanel?.tracePropagation?.(); }
function startInsnTrace() { return window.DisasmPanel?.startInsnTrace?.(); }
function stopInsnTrace() { return window.DisasmPanel?.stopInsnTrace?.(); }
function refreshTraceLog() { return window.DisasmPanel?.refreshTraceLog?.(); }

// 指针
function doPointerScan() { return window.DisasmPanel?.doPointerScan?.(); }

// 调试器
function startDebugger() { return window.DisasmPanel?.startDebugger?.(); }
function stopDebugger() { return window.DisasmPanel?.stopDebugger?.(); }
function setDebuggerBreakpoint() { return window.DisasmPanel?.setDebuggerBreakpoint?.(); }
function clearAllDebuggerBreakpoints() { return window.DisasmPanel?.clearAllDebuggerBreakpoints?.(); }
function refreshDebuggerHits() { return window.DisasmPanel?.refreshDebuggerHits?.(); }
function refreshDebuggerStatus() { return window.DisasmPanel?.refreshDebuggerStatus?.(); }

// DFG
function buildDFG() { return window.DisasmPanel?.buildDFG?.(); }
function resetDFG() { return window.DisasmPanel?.resetDFG?.(); }
function refreshDFGGraph() { return window.DisasmPanel?.refreshDFGGraph?.(); }
function refreshDFGReport() { return window.DisasmPanel?.refreshDFGReport?.(); }
function queryDFGVariable() { return window.DisasmPanel?.queryDFGVariable?.(); }

// AI
function loadProviderStatus() { return window.AIPanel?.loadProviderStatus?.(); }
function setProvider() { return window.AIPanel?.setProvider?.(); }
function aiGenerateProjectPrompt() { return window.AIPanel?.generateProjectPrompt?.(); }
function aiGeneratePrompt(type) { return window.AIPanel?.generatePrompt?.(type); }
function aiGenerateReversePrompt() { return window.AIPanel?.generateReversePrompt?.(); }

// 自动化
function startOneClickWorkflow() { return window.AutomationPanel?.startOneClickWorkflow?.(); }
function pauseWorkflow() { return window.AutomationPanel?.pauseWorkflow?.(); }
function resumeWorkflow() { return window.AutomationPanel?.resumeWorkflow?.(); }
function cancelWorkflow() { return window.AutomationPanel?.cancelWorkflow?.(); }
function generateWorkflowReport() { return window.AutomationPanel?.generateWorkflowReport?.(); }

// Agent
function startAgent() { return window.AgentPanel?.start?.(); }
function stopAgent() { return window.AgentPanel?.stop?.(); }
function agentConfirm(approved) { return window.AgentPanel?.confirm?.(approved); }

// Intent Agent (right panel + tab)
function startIntentAgent() { return window.startIntentSession?.(); }
function stopIntentAgent() { return window.stopIntentSession?.(); }
function confirmIntentAction() { return window.sendIntentResponse?.(); }
function sendIntentTask() { return window.sendIntentTask?.(); }

// 追踪
function startTrack() { return window.TrackingPanel?.startTrack?.(); }
function stopTrack() { return window.TrackingPanel?.stopTrack?.(); }
function injectTaint() { return window.TrackingPanel?.injectTaint?.(); }

// 初始化
function initApp() {
  console.log('[initApp] starting...');
  console.log('[initApp] window.api=', typeof window.api, window.api ? 'present' : 'missing');
  console.log('[initApp] window.ProcessPanel=', typeof window.ProcessPanel, window.ProcessPanel ? 'present' : 'missing');
  console.log('[initApp] window.Utils=', typeof window.Utils, window.Utils ? 'present' : 'missing');
  buildSidebar();
  if (window.ProcessPanel) { console.log('[initApp] init ProcessPanel'); window.ProcessPanel.init(); }
  if (window.MemoryPanel) { console.log('[initApp] init MemoryPanel'); window.MemoryPanel.init(); }
  if (window.TrackingPanel) { console.log('[initApp] init TrackingPanel'); window.TrackingPanel.init(); }
  if (window.DisasmPanel) { console.log('[initApp] init DisasmPanel'); window.DisasmPanel.init(); }
  if (window.AIPanel) { console.log('[initApp] init AIPanel'); window.AIPanel.init(); }
  if (window.AutomationPanel) { console.log('[initApp] init AutomationPanel'); window.AutomationPanel.init(); }
  if (window.AgentPanel) { console.log('[initApp] init AgentPanel'); window.AgentPanel.init(); }
  if (window.IntentPanel) { console.log('[initApp] init IntentPanel'); window.IntentPanel.init(); }
  updateGlobalStatus().then(() => {
    console.log('[initApp] updateGlobalStatus done, calling showAllProcesses');
    if (window.ProcessPanel) window.ProcessPanel.showAllProcesses();
  }).catch(e => {
    console.error('[initApp] updateGlobalStatus error:', e);
    if (window.ProcessPanel) window.ProcessPanel.showAllProcesses();
  });
  switchPanel('process');
  console.log('[initApp] done');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

// 定时刷新
setInterval(() => { updateGlobalStatus().catch(() => {}); }, 3000);
setInterval(() => { window.TrackingPanel?.updateWatchList?.().catch(() => {}); }, 2000);
