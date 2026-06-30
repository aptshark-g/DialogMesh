// gui/static/js/api.js — 后端 API 封装（精简版，去除死代码）
// 2026-06-24: 清理所有调用不存在旧路径的死代码函数，保留底层封装和实际被使用的 API。

const BASE = '';

// 底层请求封装（统一错误处理）
async function apiGet(url) {
  try {
    const fullUrl = BASE + url;
    console.log('GET请求:', fullUrl);
    const res = await fetch(fullUrl, { cache: 'no-store' });
    if (!res.ok) {
      console.error('HTTP错误:', res.status);
      return null;
    }
    const data = await res.json();
    console.log('GET响应:', data);
    return data;
  } catch (e) {
    console.error('GET网络错误:', e);
    if (typeof showStatus === 'function') {
      showStatus('globalStatus', '请求失败: ' + e.message);
    }
    return null;
  }
}

async function apiPost(url, body) {
  try {
    console.log('POST请求:', url, body);
    const res = await fetch(BASE + url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!res.ok) {
      console.error('POST HTTP错误:', res.status);
      return null;
    }
    const data = await res.json();
    console.log('POST响应:', data);
    return data;
  } catch (e) {
    console.error('POST网络错误:', e);
    if (typeof showStatus === 'function') {
      showStatus('globalStatus', '请求失败: ' + e.message);
    }
    return null;
  }
}

// ========== 基础 API 封装（被 panels 实际使用） ==========

function apiGetProcessList() {
  return apiGet('/api/processes');
}

function apiAttachProcess(pid) {
  return apiPost('/api/attach', { pid });
}

function apiDetachProcess() {
  console.log('apiDetachProcess: stub');
  return { status: 'ok' };
}

function apiLaunchProcess(exePath, args) {
  return apiPost('/api/launch', { exe_path: exePath, args });
}

function apiGetGlobalStatus() {
  return apiGet('/api/status');
}

function apiGetResults() {
  return apiGet('/api/results');
}

function apiGetModules() {
  return apiGet('/api/modules');
}

function apiGetRegionsLegacy() {
  return apiGet('/api/regions');
}

function apiModifyAddress(address, value) {
  return apiPost('/api/modify', { address, value });
}

function apiLockStart(addr, value, type) {
  return apiPost('/api/lock/start', { addr, value, type });
}

function apiLockStop() {
  return apiPost('/api/lock/stop');
}

function apiGetMemoryView(start, count, type) {
  return apiPost('/api/memory/view', { start, count, type });
}

// ========== Watch / Track / Lock (Legacy 兼容) ==========

function apiAddWatchLegacy(address) {
  return apiPost('/api/watch', { address });
}

function apiGetWatchLegacy() {
  return apiGet('/api/watch');
}

function apiRemoveWatchLegacy(index) {
  return apiPost('/api/watch/remove', { index });
}

function apiAddTrackLegacy(address) {
  return apiPost('/api/track/add', { address });
}

function apiInjectTaintLegacy(address, value) {
  return apiPost('/api/track/taint', { address, value });
}

// ========== Scan / Pointer (Legacy 兼容) ==========

function apiFirstScan(url, body) {
  return apiPost(url, body);
}

function apiNextScanGeneral(body) {
  return apiPost('/api/scan/next/general', body);
}

function apiPointerScanLegacy(address, maxLevel, maxOffset, addrMin, addrMax) {
  return apiPost('/api/scan/pointer', {
    address, max_level: maxLevel, max_offset: maxOffset,
    addr_min: addrMin, addr_max: addrMax
  });
}

function apiResolvePointerLegacy(module, baseOffset, offsets) {
  return apiPost('/api/pointer/resolve', { module, base_offset: baseOffset, offsets });
}

function apiWritePointerLegacy(module, baseOffset, offsets, value) {
  return apiPost('/api/pointer/write', { module, base_offset: baseOffset, offsets, value });
}

// ========== Disasm / Breakpoint / Trace (Legacy 兼容) ==========

function apiDisasmLegacy(address, count, is64) {
  return apiPost('/api/disasm', { address, count, is64 });
}

function apiFindPatternLegacy(pattern) {
  return apiPost('/api/disasm/pattern', { pattern });
}

function apiSetBpLegacy(address, mode) {
  return apiPost('/api/breakpoint/set', { address, mode });
}

function apiScanWritesLegacy(address, range) {
  return apiPost('/api/breakpoint/scan_writes', { address, range });
}

function apiTracePropagationLegacy(address, depth) {
  return apiPost('/api/breakpoint/trace_propagation', { address, depth });
}

function apiGetTraceLogLegacy(limit) {
  return apiGet('/api/trace/log?limit=' + limit);
}

// ========== Debugger API ==========

async function apiStartDebugger() {
  const r = await fetch(`${BASE}/api/debugger/start`, { method: 'POST' });
  return r.json();
}

async function apiStopDebugger() {
  const r = await fetch(`${BASE}/api/debugger/stop`, { method: 'POST' });
  return r.json();
}

async function apiSetDebuggerBp(address, size, mode) {
  const r = await fetch(`${BASE}/api/debugger/breakpoint/set`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address, size, mode })
  });
  return r.json();
}

async function apiClearDebuggerBps() {
  const r = await fetch(`${BASE}/api/debugger/breakpoint/clear_all`, { method: 'POST' });
  return r.json();
}

async function apiGetDebuggerHits() {
  const r = await fetch(`${BASE}/api/debugger/hits`);
  return r.json();
}

async function apiGetDebuggerStatus() {
  const r = await fetch(`${BASE}/api/debugger/status`);
  return r.json();
}

// ========== DFG API ==========

async function apiBuildDFG() {
  const r = await fetch(`${BASE}/api/dfg/build`, { method: 'POST' });
  return r.json();
}

async function apiResetDFG() {
  const r = await fetch(`${BASE}/api/dfg/reset`, { method: 'POST' });
  return r.json();
}

async function apiGetDFGGraph() {
  const r = await fetch(`${BASE}/api/dfg/graph`);
  return r.json();
}

async function apiGetDFGReport() {
  const r = await fetch(`${BASE}/api/dfg/report`);
  return r.json();
}

async function apiGetDFGVariable(addr) {
  const r = await fetch(`${BASE}/api/dfg/variable/${addr}`);
  return r.json();
}

// ========== AI API ==========

async function apiGenerateProjectPrompt(context) {
  const r = await fetch(`${BASE}/api/ai/generate-project`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ context, max_files: 10 })
  });
  return r.json();
}

async function apiGenerateCodePrompt(type, code, lang, context, error) {
  const r = await fetch(`${BASE}/api/ai/generate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, code, language: lang, context, error })
  });
  return r.json();
}

async function apiGenerateReversePrompt() {
  const r = await fetch(`${BASE}/api/ai/generate-reverse`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  });
  return r.json();
}

// ========== Auto Reverse API ==========

async function apiStartAutoReverse(config) {
  const r = await fetch(`${BASE}/api/auto-reverse/start`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  });
  return r.json();
}

async function apiGetAutoReverseStatus() {
  const r = await fetch(`${BASE}/api/auto-reverse/status`);
  return r.json();
}

async function apiStopAutoReverse() {
  const r = await fetch(`${BASE}/api/auto-reverse/stop`, { method: 'POST' });
  return r.json();
}

async function apiFinalizeAutoReverse() {
  const r = await fetch(`${BASE}/api/auto-reverse/finalize`, { method: 'POST' });
  return r.json();
}

async function apiGetAutoReversePrompt(taskId) {
  const r = await fetch(`${BASE}/api/auto-reverse/prompt?task_id=${taskId}`);
  return r.json();
}

// ========== Provider API ==========

async function apiGetProviders() {
  const r = await fetch(`${BASE}/api/providers`);
  return r.json();
}

async function apiSetProvider(provider) {
  const r = await fetch(`${BASE}/api/providers/${provider}/set`, { method: 'POST' });
  return r.json();
}

// ========== Workflow API ==========

async function apiStartWorkflow(config) {
  const r = await fetch('/api/workflow/start', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  });
  return r.json();
}

async function apiGetWorkflowStatus() {
  const r = await fetch('/api/workflow/status');
  return r.json();
}

async function apiPauseWorkflow() {
  const r = await fetch('/api/workflow/pause', { method: 'POST' });
  return r.json();
}

async function apiResumeWorkflow() {
  const r = await fetch('/api/workflow/resume', { method: 'POST' });
  return r.json();
}

async function apiCancelWorkflow() {
  const r = await fetch('/api/workflow/cancel', { method: 'POST' });
  return r.json();
}

async function apiGetWorkflowReport() {
  const r = await fetch('/api/workflow/report');
  return r.json();
}

// ========== 模式识别 API (Phase 9 新增) ==========

async function apiDetectPatterns() {
  const r = await fetch('/api/pattern/detect', { method: 'POST' });
  return r.json();
}

// ========== 导出到全局 API 对象 ==========

window.api = {
  get: apiGet,
  post: apiPost,

  // 基础
  getProcessList: apiGetProcessList,
  attachProcess: apiAttachProcess,
  detachProcess: apiDetachProcess,
  launchProcess: apiLaunchProcess,
  getGlobalStatus: apiGetGlobalStatus,
  getResults: apiGetResults,
  getModules: apiGetModules,
  getRegions: apiGetRegionsLegacy,
  modifyAddress: apiModifyAddress,
  lockStart: apiLockStart,
  lockStop: apiLockStop,
  getMemoryView: apiGetMemoryView,

  // Watch / Track
  addWatchLegacy: apiAddWatchLegacy,
  getWatchLegacy: apiGetWatchLegacy,
  removeWatchLegacy: apiRemoveWatchLegacy,
  addTrackLegacy: apiAddTrackLegacy,
  injectTaintLegacy: apiInjectTaintLegacy,

  // Scan / Pointer
  firstScan: apiFirstScan,
  nextScanGeneral: apiNextScanGeneral,
  pointerScanLegacy: apiPointerScanLegacy,
  resolvePointerLegacy: apiResolvePointerLegacy,
  writePointerLegacy: apiWritePointerLegacy,

  // Disasm / Breakpoint / Trace
  disasmLegacy: apiDisasmLegacy,
  findPatternLegacy: apiFindPatternLegacy,
  setBpLegacy: apiSetBpLegacy,
  scanWritesLegacy: apiScanWritesLegacy,
  tracePropagationLegacy: apiTracePropagationLegacy,
  getTraceLogLegacy: apiGetTraceLogLegacy,

  // Debugger
  startDebugger: apiStartDebugger,
  stopDebugger: apiStopDebugger,
  setDebuggerBp: apiSetDebuggerBp,
  clearDebuggerBps: apiClearDebuggerBps,
  getDebuggerHits: apiGetDebuggerHits,
  getDebuggerStatus: apiGetDebuggerStatus,

  // DFG
  buildDFG: apiBuildDFG,
  resetDFG: apiResetDFG,
  getDFGGraph: apiGetDFGGraph,
  getDFGReport: apiGetDFGReport,
  getDFGVariable: apiGetDFGVariable,

  // AI
  generateProjectPrompt: apiGenerateProjectPrompt,
  generateCodePrompt: apiGenerateCodePrompt,
  generateReversePrompt: apiGenerateReversePrompt,

  // Auto Reverse
  startAutoReverse: apiStartAutoReverse,
  getAutoReverseStatus: apiGetAutoReverseStatus,
  stopAutoReverse: apiStopAutoReverse,
  finalizeAutoReverse: apiFinalizeAutoReverse,
  getAutoReversePrompt: apiGetAutoReversePrompt,

  // Provider
  getProviders: apiGetProviders,
  setProvider: apiSetProvider,

  // Workflow
  startWorkflow: apiStartWorkflow,
  getWorkflowStatus: apiGetWorkflowStatus,
  pauseWorkflow: apiPauseWorkflow,
  resumeWorkflow: apiResumeWorkflow,
  cancelWorkflow: apiCancelWorkflow,
  getWorkflowReport: apiGetWorkflowReport,

  // Pattern Engine (Phase 9)
  detectPatterns: apiDetectPatterns,
};
