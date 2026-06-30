// panels/disasm.js
(function() {
  'use strict';

  // 面板本地状态
  let disasmResults = [];
  let pointerResults = [];
  let selectedInsnAddr = '';
  let dfgChart = null;

  // 面板初始化
  function initDisasmPanel() {
    const disasmBtn = document.getElementById('disasmBtn');
    if (disasmBtn) disasmBtn.addEventListener('click', doDisasm);

    const ptrScanBtn = document.getElementById('ptrScanBtn');
    if (ptrScanBtn) ptrScanBtn.addEventListener('click', doPointerScan);

    const bpSetBtn = document.getElementById('bpSetBtn');
    if (bpSetBtn) bpSetBtn.addEventListener('click', setBreakpoint);

    const bpClearBtn = document.getElementById('bpClearBtn');
    if (bpClearBtn) bpClearBtn.addEventListener('click', clearAllBp);

    const bpRefreshBtn = document.getElementById('bpRefreshBtn');
    if (bpRefreshBtn) bpRefreshBtn.addEventListener('click', refreshBpStatus);

    const bpScanWritesBtn = document.getElementById('bpScanWritesBtn');
    if (bpScanWritesBtn) bpScanWritesBtn.addEventListener('click', scanWrites);

    const bpTraceBtn = document.getElementById('bpTraceBtn');
    if (bpTraceBtn) bpTraceBtn.addEventListener('click', tracePropagation);

    const startTraceBtn2 = document.getElementById('startTraceBtn2');
    if (startTraceBtn2) startTraceBtn2.addEventListener('click', startInsnTrace);

    const stopTraceBtn2 = document.getElementById('stopTraceBtn2');
    if (stopTraceBtn2) stopTraceBtn2.addEventListener('click', stopInsnTrace);

    const refreshTraceBtn = document.getElementById('refreshTraceBtn');
    if (refreshTraceBtn) refreshTraceBtn.addEventListener('click', refreshTraceLog);

    const startDebuggerBtn = document.getElementById('startDebuggerBtn');
    if (startDebuggerBtn) startDebuggerBtn.addEventListener('click', startDebugger);

    const stopDebuggerBtn = document.getElementById('stopDebuggerBtn');
    if (stopDebuggerBtn) stopDebuggerBtn.addEventListener('click', stopDebugger);

    const setDebuggerBpBtn = document.getElementById('setDebuggerBpBtn');
    if (setDebuggerBpBtn) setDebuggerBpBtn.addEventListener('click', setDebuggerBreakpoint);

    const clearDebuggerBpBtn = document.getElementById('clearDebuggerBpBtn');
    if (clearDebuggerBpBtn) clearDebuggerBpBtn.addEventListener('click', clearAllDebuggerBreakpoints);

    const refreshDebuggerHitsBtn = document.getElementById('refreshDebuggerHitsBtn');
    if (refreshDebuggerHitsBtn) refreshDebuggerHitsBtn.addEventListener('click', refreshDebuggerHits);

    const refreshDebuggerStatusBtn = document.getElementById('refreshDebuggerStatusBtn');
    if (refreshDebuggerStatusBtn) refreshDebuggerStatusBtn.addEventListener('click', refreshDebuggerStatus);

    const buildDfgBtn = document.getElementById('buildDfgBtn');
    if (buildDfgBtn) buildDfgBtn.addEventListener('click', buildDFG);

    const resetDfgBtn = document.getElementById('resetDfgBtn');
    if (resetDfgBtn) resetDfgBtn.addEventListener('click', resetDFG);

    const refreshDfgGraphBtn = document.getElementById('refreshDfgGraphBtn');
    if (refreshDfgGraphBtn) refreshDfgGraphBtn.addEventListener('click', refreshDFGGraph);

    const refreshDfgReportBtn = document.getElementById('refreshDfgReportBtn');
    if (refreshDfgReportBtn) refreshDfgReportBtn.addEventListener('click', refreshDFGReport);

    const queryDfgVarBtn = document.getElementById('queryDfgVarBtn');
    if (queryDfgVarBtn) queryDfgVarBtn.addEventListener('click', queryDFGVariable);

    const gotoEipBtn = document.getElementById('gotoEipBtn');
    if (gotoEipBtn) gotoEipBtn.addEventListener('click', gotoEIP);

    const searchPatternBtn = document.getElementById('searchPatternBtn');
    if (searchPatternBtn) searchPatternBtn.addEventListener('click', searchPattern);

    const ptrWriteBtn = document.getElementById('ptrWriteBtn');
    if (ptrWriteBtn) ptrWriteBtn.addEventListener('click', doPointerChainWrite);

    const ptrResolveBtn = document.getElementById('ptrResolveBtn');
    if (ptrResolveBtn) ptrResolveBtn.addEventListener('click', doPointerChainResolve);

    // Phase 8-9: Advanced analysis buttons
    const patternDetectBtn = document.getElementById('patternDetectBtn');
    if (patternDetectBtn) patternDetectBtn.addEventListener('click', detectPatterns);

    const dfgCompareCfgBtn = document.getElementById('dfgCompareCfgBtn');
    if (dfgCompareCfgBtn) dfgCompareCfgBtn.addEventListener('click', compareDfgWithCfg);

    const dfgAnomaliesBtn = document.getElementById('dfgAnomaliesBtn');
    if (dfgAnomaliesBtn) dfgAnomaliesBtn.addEventListener('click', findDfgAnomalies);

    const ghidraAnalyzeBtn = document.getElementById('ghidraAnalyzeBtn');
    if (ghidraAnalyzeBtn) ghidraAnalyzeBtn.addEventListener('click', ghidraAnalyze);

    const ghidraDecompileBtn = document.getElementById('ghidraDecompileBtn');
    if (ghidraDecompileBtn) ghidraDecompileBtn.addEventListener('click', ghidraDecompile);

    const deobfuscateBtn = document.getElementById('deobfuscateBtn');
    if (deobfuscateBtn) deobfuscateBtn.addEventListener('click', deobfuscateCode);
  }

  // 反汇编功能
  async function doDisasm() {
    const addr = document.getElementById('disasmAddr').value;
    const count = parseInt(document.getElementById('disasmCount').value) || 30;
    const is64 = document.getElementById('disasm64').checked;

    if (!addr) { window.Utils.showStatus('disasmStatus', '请输入地址'); return; }

    window.Utils.showStatus('disasmStatus', '反汇编中...');
    const data = await window.api.post('/api/disasm', { address: addr, count, is64 });

    if (data && data.status === 'ok') {
      disasmResults = data.instructions || [];
      renderDisasmTable();
      window.Utils.showStatus('disasmStatus', `反汇编完成: ${data.count} 条指令`);

      // 自动填充断点地址
      if (disasmResults.length > 0) {
        document.getElementById('bpAddr').value = addr;
      }
    } else {
      window.Utils.showStatus('disasmStatus', '反汇编失败');
    }
  }

  function renderDisasmTable() {
    const tbody = document.querySelector('#disasmTable tbody');
    if (!tbody) return;

    tbody.innerHTML = '';
    disasmResults.forEach((insn, i) => {
      const row = tbody.insertRow();
      row.dataset.address = insn.address;
      row.insertCell(0).innerHTML = `<code style="color:#0078d4;">${insn.address}</code>`;
      row.insertCell(1).innerHTML = `<code style="font-size:12px;">${insn.bytes}</code>`;
      row.insertCell(2).innerHTML = `<b>${insn.mnemonic}</b>`;
      row.insertCell(3).textContent = insn.operands;

      const actionCell = row.insertCell(4);
      const bpBtn = document.createElement('button');
      bpBtn.style.padding = '2px 6px';
      bpBtn.style.fontSize = '12px';
      bpBtn.textContent = '断点';
      bpBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        setBpFromInsn(insn.address);
      });
      actionCell.appendChild(bpBtn);

      row.addEventListener('click', () => {
        document.querySelectorAll('#disasmTable tbody tr').forEach(r => r.classList.remove('result-row-selected'));
        row.classList.add('result-row-selected');
        selectedInsnAddr = insn.address;
        document.getElementById('bpAddr').value = insn.address;
        document.getElementById('disasmAddr').value = insn.address;
      });

      // 高亮特殊指令
      if (['call', 'jmp', 'je', 'jne', 'jb', 'ja', 'jl', 'jg', 'jbe', 'jae', 'jle', 'jge', 'ret', 'int3', 'push', 'pop'].includes(insn.mnemonic)) {
        row.style.background = '#fffbe6';
      }
      if (['mov', 'lea', 'xor', 'add', 'sub'].includes(insn.mnemonic)) {
        row.style.background = '#f0f8ff';
      }
    });
  }

  async function doPointerScan() {
    const addr = document.getElementById('ptrTargetAddr').value;
    const maxLevel = parseInt(document.getElementById('ptrMaxLevel').value) || 2;
    const maxOffsetStr = document.getElementById('ptrMaxOffset').value || '0x1000';
    const addrMin = document.getElementById('ptrAddrMin').value || '0x10000';
    const addrMax = document.getElementById('ptrAddrMax').value || '0x7FFFFFFE';

    if (!addr) { window.Utils.showStatus('pointerScanStatus', '请输入目标地址'); return; }

    let maxOffset = 0x1000;
    try { maxOffset = parseInt(maxOffsetStr, 16); } catch(e) {}

    const statusEl = document.getElementById('pointerScanStatus');
    statusEl.textContent = '指针扫描中... ⏳ (C++ DLL 加速)';
    statusEl.classList.add('scanning');
    const t0 = Date.now();
    const data = await window.api.post('/api/scan/pointer', {
      address: addr,
      max_level: maxLevel,
      max_offset: maxOffset,
      addr_min: addrMin,
      addr_max: addrMax
    });
    const t1 = Date.now();
    statusEl.classList.remove('scanning');

    if (data && data.status === 'ok') {
      pointerResults = data.results || [];
      renderPointerTable();
      statusEl.textContent = `扫描完成: ${data.count} 条指针链 (${t1-t0}ms)`;
    } else {
      statusEl.textContent = '扫描失败: ' + (data?.error || '未知错误');
    }
  }

  function renderPointerTable() {
    const tbody = document.querySelector('#pointerTable tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    pointerResults.forEach((res, i) => {
      const row = tbody.insertRow();
      row.insertCell(0).textContent = res.module || 'heap';
      row.insertCell(1).textContent = '0x' + res.base_offset.toString(16);
      row.insertCell(2).textContent = res.level;
      row.insertCell(3).textContent = '[' + (res.offsets || []).map(o => '0x' + o.toString(16)).join(' -> ') + ']';
      // Current value cell (placeholder, will be filled by resolve)
      const valCell = row.insertCell(4);
      valCell.textContent = '?';
      valCell.id = 'ptr-val-' + i;

      const actionsCell = row.insertCell(5);

      const resolveBtn = document.createElement('button');
      resolveBtn.style.padding = '2px 6px';
      resolveBtn.style.fontSize = '12px';
      resolveBtn.textContent = '解析';
      resolveBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        resolvePointerChain(i);
      });
      actionsCell.appendChild(resolveBtn);

      const watchBtn = document.createElement('button');
      watchBtn.style.padding = '2px 6px';
      watchBtn.style.fontSize = '12px';
      watchBtn.textContent = '监视地址';
      watchBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        addToWatchlist('0x' + res.address.toString(16));
      });
      actionsCell.appendChild(watchBtn);

      const writeBtn = document.createElement('button');
      writeBtn.style.padding = '2px 6px';
      writeBtn.style.fontSize = '12px';
      writeBtn.textContent = '写入';
      writeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        writeViaPointerChain(i);
      });
      actionsCell.appendChild(writeBtn);
    });
  }

  async function resolvePointerChain(index) {
    const res = pointerResults[index];
    if (!res) return;
    const statusEl = document.getElementById('pointerScanStatus');
    statusEl.textContent = '解析指针链...';
    const data = await window.api.post('/api/pointer/resolve', {
      module: res.module || 'heap',
      base_offset: res.base_offset,
      offsets: res.offsets
    });
    const valCell = document.getElementById('ptr-val-' + index);
    if (data && data.status === 'ok') {
      valCell.textContent = data.value + ' @ ' + data.address;
      statusEl.textContent = '解析成功: ' + data.address + ' = ' + data.value;
    } else {
      valCell.textContent = 'ERR';
      statusEl.textContent = '解析失败: ' + (data?.error || '未知错误');
    }
  }

  async function writeViaPointerChain(index) {
    const res = pointerResults[index];
    if (!res) return;
    const scanTypeEl = document.getElementById('scanType');
    const typeName = scanTypeEl ? scanTypeEl.options[scanTypeEl.selectedIndex].text : '双字';
    const value = prompt('输入新值 (当前类型: ' + typeName + '):');
    if (value === null) return;
    const statusEl = document.getElementById('pointerScanStatus');
    statusEl.textContent = '指针链写入中...';
    const data = await window.api.post('/api/pointer/write', {
      module: res.module || 'heap',
      base_offset: res.base_offset,
      offsets: res.offsets,
      value: value
    });
    if (data && data.status === 'ok') {
      statusEl.textContent = '指针链写入成功!';
      // Auto-resolve to show new value
      await resolvePointerChain(index);
    } else {
      statusEl.textContent = '写入失败: ' + (data?.error || '未知错误');
    }
  }

  async function addToWatchlist(addr) {
    // Convert numeric address to hex string for API
    const addrStr = typeof addr === 'number' ? '0x' + addr.toString(16) : addr;
    const data = await window.api.post('/api/watch', { address: addrStr });
    if (data && data.status === 'ok') {
      window.Utils.showStatus('pointerScanStatus', '已添加监视: ' + addrStr);
      window.TrackingPanel.updateWatchList();
    }
  }

  // 指针链写入 (Phase 3: Basic CE Tab)
  async function doPointerChainWrite() {
    const module = document.getElementById('ptrWriteModule').value;
    const baseOffsetStr = document.getElementById('ptrWriteBaseOffset').value;
    const offsetsStr = document.getElementById('ptrWriteOffsets').value;
    const value = document.getElementById('ptrWriteValue').value;
    const statusEl = document.getElementById('ptrWriteStatus');

    if (!module || !value) { statusEl.textContent = '请输入模块名和新值'; return; }

    let baseOffset = 0;
    try { baseOffset = parseInt(baseOffsetStr, 0); } catch(e) {}

    let offsets = [];
    if (offsetsStr) {
      offsets = offsetsStr.split(/->|->|,/)
        .map(s => s.trim().replace(/^0x/i, ''))
        .filter(s => s)
        .map(s => parseInt(s, 16));
    }

    statusEl.textContent = '指针链写入中...';
    const data = await window.api.post('/api/pointer/write', {
      module: module,
      base_offset: baseOffset,
      offsets: offsets,
      value: value
    });
    if (data && data.status === 'ok') {
      statusEl.textContent = '指针链写入成功!';
    } else {
      statusEl.textContent = '写入失败: ' + (data?.error || '未知错误');
    }
  }

  async function doPointerChainResolve() {
    const module = document.getElementById('ptrWriteModule').value;
    const baseOffsetStr = document.getElementById('ptrWriteBaseOffset').value;
    const offsetsStr = document.getElementById('ptrWriteOffsets').value;
    const statusEl = document.getElementById('ptrWriteStatus');

    if (!module) { statusEl.textContent = '请输入模块名'; return; }

    let baseOffset = 0;
    try { baseOffset = parseInt(baseOffsetStr, 0); } catch(e) {}

    let offsets = [];
    if (offsetsStr) {
      offsets = offsetsStr.split(/->|->|,/)
        .map(s => s.trim().replace(/^0x/i, ''))
        .filter(s => s)
        .map(s => parseInt(s, 16));
    }

    statusEl.textContent = '解析指针链...';
    const data = await window.api.post('/api/pointer/resolve', {
      module: module,
      base_offset: baseOffset,
      offsets: offsets
    });
    if (data && data.status === 'ok') {
      statusEl.textContent = '解析成功: ' + data.address + ' = ' + data.value;
    } else {
      statusEl.textContent = '解析失败: ' + (data?.error || '未知错误');
    }
  }

  async function gotoEIP() {
    // 从扫描结果自动跳转
    const firstAddr = window.scanResults.length > 0 ? window.scanResults[0].address : null;
    if (firstAddr) {
      document.getElementById('disasmAddr').value = firstAddr;
      doDisasm();
    } else {
      window.Utils.showStatus('disasmStatus', '请先进行一次内存扫描以定位代码区域');
    }
  }

  async function searchPattern() {
    const pattern = document.getElementById('patternHex').value;
    if (!pattern) { window.Utils.showStatus('disasmStatus', '请输入特征码'); return; }

    window.Utils.showStatus('disasmStatus', '搜索中... (可能较慢)');
    const data = await window.api.post('/api/disasm/pattern', { pattern });

    if (data && data.status === 'ok') {
      const results = data.results || [];
      if (results.length > 0) {
        document.getElementById('disasmAddr').value = results[0];
        window.Utils.showStatus('disasmStatus', `找到 ${data.count} 个匹配，已跳转到第一个`);
        doDisasm();
      } else {
        window.Utils.showStatus('disasmStatus', '未找到匹配');
      }
    } else {
      window.Utils.showStatus('disasmStatus', '搜索失败');
    }
  }

  // 内存断点功能
  async function setBreakpoint() {
    const addr = document.getElementById('bpAddr').value;
    const mode = document.getElementById('bpMode').value;
    if (!addr) { window.Utils.showStatus('bpStatus', '请输入地址'); return; }

    const data = await window.api.post('/api/breakpoint/set', { address: addr, mode });
    if (data && data.status === 'ok') {
      window.Utils.showStatus('bpStatus', `断点已设置: ${addr} (${mode})`);
      refreshBpStatus();
    } else {
      window.Utils.showStatus('bpStatus', '设置失败: ' + (data?.message || 'unknown'));
    }
  }

  function setBpFromInsn(addr) {
    document.getElementById('bpAddr').value = addr;
    document.getElementById('bpMode').value = 'write';
    setBreakpoint();
  }

  async function clearAllBp() {
    await window.api.post('/api/breakpoint/clear_all', {});
    window.Utils.showStatus('bpStatus', '已清除所有断点');
    refreshBpStatus();
  }

  async function refreshBpStatus() {
    const [statusData, hitsData] = await Promise.all([
      window.api.get('/api/breakpoint/status'),
      window.api.get('/api/breakpoint/hits')
    ]);

    const bps = statusData?.breakpoints || [];
    const hits = hitsData?.hits || [];
    window.Utils.showStatus('bpStatus', `断点数: ${bps.length}, 命中: ${hits.length}`);

    // 渲染断点表
    const tbody = document.querySelector('#bpTable tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    // 合并断点和命中信息
    bps.forEach(bp => {
      const row = tbody.insertRow();
      row.insertCell(0).textContent = bp.address;
      row.insertCell(1).textContent = bp.mode;
      row.insertCell(2).textContent = bp.hit_count;
      row.insertCell(3).textContent = bp.last_hit?.old_value || '-';
      row.insertCell(4).textContent = bp.last_hit?.new_value || '-';
    });
  }

  async function scanWrites() {
    const addr = document.getElementById('bpAddr').value;
    if (!addr) { window.Utils.showStatus('bpStatus', '请先输入/选择地址'); return; }

    window.Utils.showStatus('bpStatus', '扫描附近写入指令...');
    const data = await window.api.post('/api/breakpoint/scan_writes', { address: addr, range: 0x2000 });

    if (data && data.status === 'ok') {
      disasmResults = data.instructions || [];
      renderDisasmTable();
      window.Utils.showStatus('bpStatus', `找到 ${data.count} 条可能写入的指令`);
    } else {
      window.Utils.showStatus('bpStatus', '扫描失败');
    }
  }

  async function tracePropagation() {
    const addr = document.getElementById('bpAddr').value;
    if (!addr) { window.Utils.showStatus('bpStatus', '请先输入/选择地址'); return; }

    window.Utils.showStatus('bpStatus', '追踪数据传播链...');
    const data = await window.api.post('/api/breakpoint/trace_propagation', { address: addr, depth: 3 });

    if (data && data.status === 'ok') {
      const chains = data.chains || [];
      if (chains.length > 0) {
        // 将追踪链作为反汇编结果显示，跳转到第一个
        document.getElementById('disasmAddr').value = `0x${chains[0].instruction_addr.toString(16)}`;
        doDisasm();
      }
      window.Utils.showStatus('bpStatus', `找到 ${data.count} 条传播链`);
    } else {
      window.Utils.showStatus('bpStatus', '追踪失败');
    }
  }

  // 指令追踪功能
  async function startInsnTrace() {
    const data = await window.api.post('/api/trace/start', {});
    if (data && data.status === 'ok') {
      document.getElementById('startTraceBtn2').disabled = true;
      document.getElementById('stopTraceBtn2').disabled = false;
      window.Utils.showStatus('traceStatus', '正在追踪...（操作目标程序以收集数据）');
    } else {
      window.Utils.showStatus('traceStatus', '启动失败');
    }
  }

  async function stopInsnTrace() {
    const data = await window.api.post('/api/trace/stop', {});
    document.getElementById('startTraceBtn2').disabled = false;
    document.getElementById('stopTraceBtn2').disabled = true;

    if (data) {
      const stats = data.stats || {};
      const trace = data.trace || [];
      const jumps = data.jumps || [];

      window.Utils.showStatus('traceStatus',
        `追踪完成: ${stats.total_instructions || 0} 条指令, ` +
        `${stats.unique_addresses || 0} 个唯一地址, ${jumps.length} 次跳转`
      );

      // 渲染追踪表
      const tbody = document.querySelector('#traceTable tbody');
      if (!tbody) return;
      tbody.innerHTML = '';
      trace.slice(-100).forEach(e => {
        const row = tbody.insertRow();
        row.insertCell(0).textContent = e.timestamp;
        row.insertCell(1).innerHTML = `<code>${e.address}</code>`;
        row.insertCell(2).innerHTML = `<b>${e.mnemonic}</b>`;
        row.insertCell(3).textContent = e.operands;
        row.insertCell(4).innerHTML = `<code style="font-size:11px;">${e.bytes}</code>`;
      });
    }
  }

  async function refreshTraceLog() {
    const data = await window.api.get('/api/trace/log?limit=100');
    if (!data) return;

    window.Utils.showStatus('traceStatus', `当前追踪中: ${data.count} 条记录`);

    const tbody = document.querySelector('#traceTable tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    (data.log || []).forEach(e => {
      const row = tbody.insertRow();
      row.insertCell(0).textContent = e.timestamp;
      row.insertCell(1).innerHTML = `<code>${e.address}</code>`;
      row.insertCell(2).innerHTML = `<b>${e.mnemonic}</b>`;
      row.insertCell(3).textContent = e.operands;
      row.insertCell(4).innerHTML = `<code style="font-size:11px;">${e.bytes}</code>`;
    });
  }

  // Debugger API
  async function startDebugger() {
    try {
      const j = await window.api.post('/api/debugger/start', {});
      if (j && j.status === 'ok') {
        document.getElementById('startDebuggerBtn').disabled = true;
        document.getElementById('stopDebuggerBtn').disabled = false;
        document.getElementById('debuggerStatus').textContent = '运行中';
        document.getElementById('debuggerStatus').style.color = '#28a745';
      } else {
        alert('启动调试器失败: ' + (j?.message || j?.error));
      }
    } catch (e) {
      alert('启动调试器异常: ' + e);
    }
  }

  async function stopDebugger() {
    try {
      const j = await window.api.post('/api/debugger/stop', {});
      document.getElementById('startDebuggerBtn').disabled = false;
      document.getElementById('stopDebuggerBtn').disabled = true;
      document.getElementById('debuggerStatus').textContent = '已停止';
      document.getElementById('debuggerStatus').style.color = '#999';
    } catch (e) {
      alert('停止调试器异常: ' + e);
    }
  }

  async function setDebuggerBreakpoint() {
    const addr = document.getElementById('dbBpAddr').value;
    const size = parseInt(document.getElementById('bpSize').value) || 4;
    const mode = document.getElementById('dbBpMode').value;
    if (!addr) { alert('请输入地址'); return; }
    try {
      const j = await window.api.post('/api/debugger/breakpoint/set', { address: addr, size: size, mode: mode });
      if (j && j.status === 'ok') {
        alert(j.message);
        refreshDebuggerStatus();
      } else {
        alert('设置断点失败: ' + (j?.message || j?.error));
      }
    } catch (e) { alert('设置断点异常: ' + e); }
  }

  async function clearAllDebuggerBreakpoints() {
    try {
      await window.api.post('/api/debugger/breakpoint/clear_all', {});
      refreshDebuggerStatus();
    } catch (e) { alert('清除断点异常: ' + e); }
  }

  async function refreshDebuggerHits() {
    try {
      const j = await window.api.get('/api/debugger/hits');
      if (!j) return;
      const tbody = document.querySelector('#debuggerHitTable tbody');
      tbody.innerHTML = '';
      j.hits.forEach((h, idx) => {
        const tr = document.createElement('tr');
        const rip = h.rip ? '0x' + h.rip.toString(16) : '?';
        const module = h.module_name || '';
        const codeCtx = h.code_context || '';
        const val = h.new_value || '';
        let stack = '';
        if (h.call_stack && h.call_stack.length > 0) {
          stack = h.call_stack.map((a, i) => 'F' + i + ': 0x' + a.toString(16)).join('<br>');
        } else {
          stack = '-';
        }
        tr.innerHTML = `<td>${idx + 1}</td><td>${rip}</td><td>${module}</td><td style="font-family:monospace;font-size:12px;max-width:200px;overflow:hidden;">${codeCtx}</td><td>${val}</td><td style="font-size:12px;">${stack}</td><td>${h.timestamp_ms || ''}</td>`;
        tbody.appendChild(tr);
      });
      document.getElementById('debuggerHitCount').textContent = j.count + ' hits';
    } catch (e) { console.error('refreshDebuggerHits:', e); }
  }

  async function refreshDebuggerStatus() {
    try {
      const j = await window.api.get('/api/debugger/status');
      if (!j) return;
      const tbody = document.querySelector('#debuggerStatusTable tbody');
      tbody.innerHTML = '';
      j.breakpoints.forEach(bp => {
        const tr = document.createElement('tr');
        const modeNames = { 0: 'exec', 1: 'read', 2: 'write', 3: 'access' };
        tr.innerHTML = `<td>${bp.addr ? '0x' + bp.addr.toString(16) : '?'}</td><td>${modeNames[bp.mode] || bp.mode}</td>`;
        tbody.appendChild(tr);
      });
    } catch (e) { console.error('refreshDebuggerStatus:', e); }
  }

  // DFG Functions
  async function buildDFG() {
    try {
      const j = await window.api.post('/api/dfg/build', {});
      if (j && j.status === 'ok') {
        document.getElementById('dfgStats').textContent = `Nodes: ${j.stats.node_count}, Edges: ${j.stats.edge_count}`;
        refreshDFGGraph();
      }
    } catch (e) { alert('Build DFG failed: ' + e); }
  }

  async function resetDFG() {
    try {
      await window.api.post('/api/dfg/reset', {});
      document.getElementById('dfgStats').textContent = 'Nodes: 0, Edges: 0';
      if (dfgChart) dfgChart.clear();
      document.getElementById('dfgReport').textContent = '暂无数据';
    } catch (e) { alert('Reset DFG failed: ' + e); }
  }

  async function refreshDFGGraph() {
    try {
      const j = await window.api.get('/api/dfg/graph');
      if (!j) return;
      document.getElementById('dfgStats').textContent = `Nodes: ${j.stats.node_count}, Edges: ${j.stats.edge_count}`;
      if (!dfgChart) {
        dfgChart = echarts.init(document.getElementById('dfgChart'));
      }
      dfgChart.setOption({
        title: { text: 'Data Flow Graph', left: 'center' },
        tooltip: {},
        legend: [{ data: j.categories.map(c => c.name) }],
        series: [{
          type: 'graph',
          layout: 'force',
          animation: true,
          roam: true,
          label: { show: true, position: 'right', formatter: '{b}' },
          edgeSymbol: ['circle', 'arrow'],
          edgeSymbolSize: [4, 10],
          data: j.nodes,
          links: j.edges,
          categories: j.categories,
          force: { repulsion: 100, edgeLength: 100 },
          lineStyle: { curveness: 0.2 }
        }]
      });
    } catch (e) { console.error('refreshDFGGraph:', e); }
  }

  async function refreshDFGReport() {
    try {
      const j = await window.api.get('/api/dfg/report');
      if (!j) return;
      let text = `=== DFG Reverse Engineering Report ===\n`;
      text += `Nodes: ${j.stats.total_nodes}, Edges: ${j.stats.total_edges}\n`;
      text += `Variables: ${j.stats.variable_count}, Instructions: ${j.stats.instruction_count}\n\n`;
      text += `--- Variables ---\n`;
      j.variables.forEach(v => {
        text += `${v.address} = ${v.value || '?'} (size=${v.size}, accesses=${v.access_count})\n`;
        if (v.writers.length > 0) {
          text += `  Writers: ${v.writers.map(w => `0x${w.rip.toString(16)} [${w.module || '?'}]`).join(', ')}\n`;
        }
        if (v.readers.length > 0) {
          text += `  Readers: ${v.readers.map(r => `0x${r.rip.toString(16)} [${r.module || '?'}]`).join(', ')}\n`;
        }
      });
      text += `\n--- Instructions ---\n`;
      j.instructions.forEach(i => {
        text += `0x${i.rip} [${i.module || '?'}] hits=${i.hit_count}\n`;
        text += `  Code: ${i.code_context || '?'}\n`;
        text += `  Accesses: ${i.accesses.map(a => `${a.type} ${a.address}`).join(', ')}\n`;
        if (i.call_chain.length > 0) {
          text += `  Call chain: ${i.call_chain.join(' -> ')}\n`;
        }
      });
      document.getElementById('dfgReport').textContent = text;
    } catch (e) { console.error('refreshDFGReport:', e); }
  }

  async function queryDFGVariable() {
    const addr = document.getElementById('dfgVarAddr').value;
    if (!addr) { alert('Please enter an address'); return; }
    try {
      const j = await window.api.get('/api/dfg/variable/' + addr);
      if (!j) return;
      const tbody = document.querySelector('#dfgVarTable tbody');
      tbody.innerHTML = '';
      if (j.dependencies) {
        j.dependencies.forEach(dep => {
          const tr = document.createElement('tr');
          tr.innerHTML = `<td>${dep.rip ? '0x' + dep.rip.toString(16) : '?'}</td><td>${dep.type}</td><td>${dep.count}</td><td>${dep.module || ''}</td><td style="font-family:monospace;font-size:12px;">${dep.code_context || ''}</td>`;
          tbody.appendChild(tr);
        });
      }
    } catch (e) { alert('Query failed: ' + e); }
  }

  // ============================================================
  // Phase 8-9: Advanced Analysis Functions
  // ============================================================

  async function detectPatterns() {
    const reportEl = document.getElementById('advancedAnalysisReport');
    const statusEl = document.getElementById('advancedAnalysisStatus');
    statusEl.textContent = '模式识别分析中...';
    reportEl.textContent = '正在分析断点命中模式...';
    try {
      const j = await window.api.post('/api/pattern/detect', {});
      if (!j) { statusEl.textContent = '请求失败'; return; }
      if (j.status === 'no_data') {
        reportEl.textContent = '暂无断点命中数据。请先设置断点并等待命中。';
        statusEl.textContent = '无数据';
        return;
      }
      let text = `=== 模式识别结果 ===\n`;
      text += `检测到 ${j.summary?.total_patterns || 0} 个模式，`;
      text += `${j.summary?.total_hits || 0} 次命中，${j.summary?.unique_addresses || 0} 个地址\n\n`;
      if (j.patterns) {
        j.patterns.forEach((p, i) => {
          text += `[${i+1}] ${p.pattern_type.toUpperCase()} | 置信度 ${(p.confidence*100).toFixed(1)}%\n`;
          text += `    地址: ${p.address}\n`;
          text += `    描述: ${p.description}\n`;
          text += `    命中: ${p.hit_count} 次，平均间隔: ${(p.avg_interval*1000).toFixed(1)}ms\n`;
          if (p.suggested_action) {
            text += `    建议: ${p.suggested_action}\n`;
          }
          text += `\n`;
        });
      }
      reportEl.textContent = text;
      statusEl.textContent = `完成: ${j.summary?.total_patterns || 0} 个模式`;
    } catch (e) {
      console.error('detectPatterns:', e);
      reportEl.textContent = '模式识别失败: ' + e.message;
      statusEl.textContent = '错误';
    }
  }

  async function compareDfgWithCfg() {
    const reportEl = document.getElementById('advancedAnalysisReport');
    const statusEl = document.getElementById('advancedAnalysisStatus');
    statusEl.textContent = 'DFG-CFG 对比中...';
    reportEl.textContent = '正在对比 DFG 动态边与 Angr CFG 静态边...';
    try {
      const j = await window.api.post('/api/dfg/compare_cfg', { function_address: '' });
      if (!j) { statusEl.textContent = '请求失败'; return; }
      let text = `=== DFG vs CFG 对比结果 ===\n`;
      text += `DFG 动态边: ${j.dfg_edge_count}\n`;
      text += `CFG 静态边: ${j.cfg_edge_count}\n`;
      text += `确认边: ${j.confirmed_edges} (覆盖率 ${j.coverage_percent}%)\n`;
      text += `DFG 独有 (运行时生成): ${j.dynamic_only_edges}\n`;
      text += `CFG 独有 (未触发): ${j.static_only_edges}\n\n`;
      if (j.anomalous_dataflow && j.anomalous_dataflow.length > 0) {
        text += `--- 异常数据流 (${j.anomalous_dataflow.length}) ---\n`;
        j.anomalous_dataflow.forEach((a, i) => {
          text += `  [${i+1}] 跨块数据流: ${a.source} -> ${a.target}\n`;
          text += `      原因: ${a.reason}\n`;
        });
      }
      reportEl.textContent = text;
      statusEl.textContent = `覆盖率 ${j.coverage_percent}%`;
    } catch (e) {
      console.error('compareDfgWithCfg:', e);
      reportEl.textContent = 'DFG-CFG 对比失败: ' + e.message;
      statusEl.textContent = '错误';
    }
  }

  async function findDfgAnomalies() {
    const reportEl = document.getElementById('advancedAnalysisReport');
    const statusEl = document.getElementById('advancedAnalysisStatus');
    statusEl.textContent = '异常检测中...';
    reportEl.textContent = '正在检测 DFG 异常数据流...';
    try {
      const j = await window.api.get('/api/dfg/anomalies');
      if (!j) { statusEl.textContent = '请求失败'; return; }
      let text = `=== DFG 异常数据流检测结果 ===\n`;
      text += `异常路径数: ${j.anomaly_count}\n\n`;
      if (j.anomalies && j.anomalies.length > 0) {
        j.anomalies.forEach((a, i) => {
          text += `[${i+1}] ${a.source} -> ${a.target}\n`;
          text += `    原因: ${a.reason}\n`;
          text += `    建议: ${a.suggestion}\n\n`;
        });
      } else {
        text += '未发现异常数据流。\n';
      }
      reportEl.textContent = text;
      statusEl.textContent = `${j.anomaly_count} 个异常`;
    } catch (e) {
      console.error('findDfgAnomalies:', e);
      reportEl.textContent = '异常检测失败: ' + e.message;
      statusEl.textContent = '错误';
    }
  }

  async function ghidraAnalyze() {
    const reportEl = document.getElementById('advancedAnalysisReport');
    const statusEl = document.getElementById('advancedAnalysisStatus');
    statusEl.textContent = 'Ghidra 分析中...';
    reportEl.textContent = '正在调用 Ghidra Headless 分析...';
    try {
      const j = await window.api.post('/api/ghidra/analyze', { analyze: true, run_scripts: true });
      if (!j) { statusEl.textContent = '请求失败'; return; }
      let text = `=== Ghidra 分析结果 ===\n`;
      text += `状态: ${j.status}\n`;
      if (j.results) {
        text += `\n函数: ${j.results.functions_count}\n`;
        text += `符号: ${j.results.symbols_count}\n`;
        text += `字符串: ${j.results.strings_count}\n`;
      }
      if (j.error) {
        text += `\n错误: ${j.error}\n`;
      }
      reportEl.textContent = text;
      statusEl.textContent = j.status;
    } catch (e) {
      console.error('ghidraAnalyze:', e);
      reportEl.textContent = 'Ghidra 分析失败: ' + e.message + '\n\n提示: 确保 Ghidra 已安装且路径正确。';
      statusEl.textContent = '错误';
    }
  }

  async function ghidraDecompile() {
    const reportEl = document.getElementById('advancedAnalysisReport');
    const statusEl = document.getElementById('advancedAnalysisStatus');
    const addr = prompt('输入函数地址 (hex):', '0x');
    if (!addr) return;
    statusEl.textContent = 'Ghidra 反编译中...';
    reportEl.textContent = '正在调用 Ghidra 反编译...';
    try {
      const j = await window.api.get('/api/ghidra/decompile?address=' + encodeURIComponent(addr));
      if (!j) { statusEl.textContent = '请求失败'; return; }
      let text = `=== Ghidra 反编译: ${addr} ===\n\n`;
      text += j.c_code || '无反编译结果';
      if (j.error) {
        text += `\n\n错误: ${j.error}\n`;
      }
      reportEl.textContent = text;
      statusEl.textContent = j.status || '完成';
    } catch (e) {
      console.error('ghidraDecompile:', e);
      reportEl.textContent = 'Ghidra 反编译失败: ' + e.message;
      statusEl.textContent = '错误';
    }
  }

  async function deobfuscateCode() {
    const reportEl = document.getElementById('advancedAnalysisReport');
    const statusEl = document.getElementById('advancedAnalysisStatus');
    statusEl.textContent = '反混淆检测中...';
    reportEl.textContent = '正在检测保护壳与混淆...';
    try {
      const j = await window.api.post('/api/deobfuscator/analyze_protection', {});
      if (!j) { statusEl.textContent = '请求失败'; return; }
      let text = `=== 反混淆/保护分析 ===\n`;
      text += `状态: ${j.status}\n\n`;
      if (j.techniques) {
        text += `检测到的技术 (${j.techniques.length}):\n`;
        j.techniques.forEach((t, i) => {
          text += `  [${i+1}] ${t.name} (置信度 ${(t.confidence*100).toFixed(1)}%)\n`;
          if (t.addresses && t.addresses.length > 0) {
            text += `      地址: ${t.addresses.map(a => '0x'+a.toString(16)).join(', ')}\n`;
          }
        });
      }
      if (j.bypass_results) {
        text += `\n绕过结果: ${JSON.stringify(j.bypass_results, null, 2)}\n`;
      }
      reportEl.textContent = text;
      statusEl.textContent = `${j.techniques?.length || 0} 个技术`;
    } catch (e) {
      console.error('deobfuscateCode:', e);
      reportEl.textContent = '反混淆检测失败: ' + e.message;
      statusEl.textContent = '错误';
    }
  }

  // 导出到全局
  window.DisasmPanel = {
    init: initDisasmPanel,
    doDisasm: doDisasm,
    renderDisasmTable: renderDisasmTable,
    doPointerScan: doPointerScan,
    renderPointerTable: renderPointerTable,
    resolvePointerChain: resolvePointerChain,
    writeViaPointerChain: writeViaPointerChain,
    addToWatchlist: addToWatchlist,
    doPointerChainWrite: doPointerChainWrite,
    doPointerChainResolve: doPointerChainResolve,
    gotoEIP: gotoEIP,
    searchPattern: searchPattern,
    setBreakpoint: setBreakpoint,
    setBpFromInsn: setBpFromInsn,
    clearAllBp: clearAllBp,
    refreshBpStatus: refreshBpStatus,
    scanWrites: scanWrites,
    tracePropagation: tracePropagation,
    startInsnTrace: startInsnTrace,
    stopInsnTrace: stopInsnTrace,
    refreshTraceLog: refreshTraceLog,
    startDebugger: startDebugger,
    stopDebugger: stopDebugger,
    setDebuggerBreakpoint: setDebuggerBreakpoint,
    clearAllDebuggerBreakpoints: clearAllDebuggerBreakpoints,
    refreshDebuggerHits: refreshDebuggerHits,
    refreshDebuggerStatus: refreshDebuggerStatus,
    buildDFG: buildDFG,
    resetDFG: resetDFG,
    refreshDFGGraph: refreshDFGGraph,
    refreshDFGReport: refreshDFGReport,
    queryDFGVariable: queryDFGVariable,
    // Phase 8-9 Advanced Analysis
    detectPatterns: detectPatterns,
    compareDfgWithCfg: compareDfgWithCfg,
    findDfgAnomalies: findDfgAnomalies,
    ghidraAnalyze: ghidraAnalyze,
    ghidraDecompile: ghidraDecompile,
    deobfuscateCode: deobfuscateCode,
  };
})();