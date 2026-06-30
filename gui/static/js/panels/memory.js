// panels/memory.js
(function() {
  'use strict';

  // 面板本地状态
  let filteredResults = [];
  let lastScanType = 2;
  let sortColumn = '';
  let sortDirection = 'asc';

  // 内存查看器本地状态
  const MEM_ROW_HEIGHT = 24;
  const MEM_VIEW_COUNT = 10000;
  let memDataCache = [];
  let memStartAddr = 0;
  let memTypeSize = 4;
  let memType = 2;
  let memSelectionStart = -1;
  let memSelectionEnd = -1;
  let memIsSelecting = false;
  let memLastValues = {};

  // 面板初始化
  function initMemoryPanel() {
    const scanMode = document.getElementById('scanMode');
    if (scanMode) scanMode.addEventListener('change', onScanModeChange);

    const firstScanBtn = document.getElementById('firstScanBtn');
    if (firstScanBtn) firstScanBtn.addEventListener('click', firstScan);

    const nextScanBtn = document.getElementById('nextScanBtn');
    if (nextScanBtn) nextScanBtn.addEventListener('click', nextScan);

    const refreshResultsBtn = document.getElementById('refreshResultsBtn');
    if (refreshResultsBtn) refreshResultsBtn.addEventListener('click', refreshResults);

    const modifyBtn = document.getElementById('modifyBtn');
    if (modifyBtn) modifyBtn.addEventListener('click', modifySelected);

    const addWatchBtn = document.getElementById('addWatchBtn');
    if (addWatchBtn) addWatchBtn.addEventListener('click', addToWatch);

    const resultFilter = document.getElementById('resultFilter');
    if (resultFilter) resultFilter.addEventListener('input', filterResults);

    const thAddress = document.getElementById('th-address');
    if (thAddress) thAddress.addEventListener('click', () => sortResults('address'));

    const thValue = document.getElementById('th-value');
    if (thValue) thValue.addEventListener('click', () => sortResults('value'));

    const memViewContainer = document.getElementById('memViewContainer');
    if (memViewContainer) {
      memViewContainer.addEventListener('scroll', () => {
        requestAnimationFrame(renderMemView);
      });
    }

    document.addEventListener('mouseup', () => {
      if (memIsSelecting) {
        endMemSelect();
      }
    });

    const autoFollowBtn = document.getElementById('autoFollowBtn');
    if (autoFollowBtn) autoFollowBtn.addEventListener('click', autoFollowFirstScan);

    const trackMemBtn = document.getElementById('trackMemBtn');
    if (trackMemBtn) trackMemBtn.addEventListener('click', trackSelectedMemory);

    const clearSelBtn = document.getElementById('clearSelBtn');
    if (clearSelBtn) clearSelBtn.addEventListener('click', clearMemorySelection);

    const refreshMemBtn = document.getElementById('refreshMemBtn');
    if (refreshMemBtn) refreshMemBtn.addEventListener('click', refreshMemoryView);

    const regionsBtn = document.getElementById('regionsBtn');
    if (regionsBtn) regionsBtn.addEventListener('click', showMemoryRegions);
  }

  // Scan mode UI handler
  function onScanModeChange() {
    const mode = document.getElementById('scanMode').value;
    document.getElementById('scanValueRow').style.display = (mode === 'exact' || mode === 'unknown') ? '' : 'none';
    document.getElementById('scanRangeRow').style.display = (mode === 'between') ? '' : 'none';
    document.getElementById('scanHexRow').style.display = (mode === 'bytearray') ? '' : 'none';
  }

  // 扫描功能
  async function firstScan() {
    await window.ProcessPanel.updateGlobalStatus();
    if (!window.attached) { window.Utils.showStatus('scanStatus', '请先附加进程'); return; }

    const scanTypeEl = document.getElementById('scanType');
    const scanModeEl = document.getElementById('scanMode');
    const mode = scanModeEl ? scanModeEl.value : 'exact';
    const type = scanTypeEl ? parseInt(scanTypeEl.value) : 2;

    let url = '/api/scan/first';
    let body = { type };
    let statusText = '';

    if (mode === 'exact') {
      const value = document.getElementById('scanValue').value;
      if (!value) { window.Utils.showStatus('scanStatus', '请输入扫描值'); return; }
      body.value = value;
      statusText = `精确值扫描完成`;
    } else if (mode === 'unknown') {
      url = '/api/scan/first/unknown';
      statusText = `未知初始值扫描完成`;
    } else if (mode === 'between') {
      const minVal = document.getElementById('scanMin').value;
      const maxVal = document.getElementById('scanMax').value;
      if (!minVal || !maxVal) { window.Utils.showStatus('scanStatus', '请输入范围值'); return; }
      url = '/api/scan/first/between';
      body.min = minVal;
      body.max = maxVal;
      statusText = `范围扫描完成`;
    } else if (mode === 'bytearray') {
      const hexStr = document.getElementById('scanHex').value;
      if (!hexStr) { window.Utils.showStatus('scanStatus', '请输入特征码'); return; }
      url = '/api/scan/first/bytearray';
      body.hex = hexStr;
      statusText = `字节数组扫描完成`;
    }

    lastScanType = type;
    const data = await window.api.post(url, body);

    if (!data || data.error) {
      window.Utils.showStatus('scanStatus', data?.error || '扫描失败');
      return;
    }

    window.scanResults = data.results || [];
    filteredResults = [...window.scanResults];
    sortColumn = '';
    sortDirection = 'asc';

    window.Utils.showStatus('scanStatus', `${statusText}，找到 ${data.count} 个地址`);
    renderResultTable();
  }

  async function nextScan() {
    if (!window.attached) { window.Utils.showStatus('scanStatus', '请先附加进程'); return; }

    const scanModeEl = document.getElementById('scanMode');
    const mode = scanModeEl ? scanModeEl.value : 'exact';
    const scanTypeEl = document.getElementById('scanType');
    const type = scanTypeEl ? parseInt(scanTypeEl.value) : 2;

    let body = {};
    let statusText = '';

    if (mode === 'exact') {
      const value = document.getElementById('scanValue').value;
      if (!value) { window.Utils.showStatus('scanStatus', '请输入扫描值'); return; }
      body.mode = 0; // SCAN_TYPE_EXACT
      body.value = value;
      statusText = `精确值再次扫描`;
    } else if (mode === 'unknown') {
      body.mode = 2; // SCAN_TYPE_CHANGED
      statusText = `变动扫描`;
    } else if (mode === 'between') {
      const minVal = document.getElementById('scanMin').value;
      const maxVal = document.getElementById('scanMax').value;
      body.mode = 6; // SCAN_TYPE_BETWEEN
      body.min = minVal;
      body.max = maxVal;
      statusText = `范围再次扫描`;
    } else if (mode === 'bytearray') {
      window.Utils.showStatus('scanStatus', '字节数组不支持再次扫描');
      return;
    }

    const data = await window.api.post('/api/scan/next/general', body);

    if (!data || data.error) {
      window.Utils.showStatus('scanStatus', data?.error || '再次扫描失败');
      return;
    }

    window.scanResults = data.results || [];
    filteredResults = [...window.scanResults];
    sortColumn = '';
    sortDirection = 'asc';

    window.Utils.showStatus('scanStatus', `${statusText}后剩余 ${data.count} 个地址`);
    renderResultTable();
  }

  // 结果搜索
  function filterResults() {
    const resultFilter = document.getElementById('resultFilter');
    const filter = resultFilter ? resultFilter.value.toLowerCase() : '';

    if (!filter) {
      filteredResults = [...window.scanResults];
    } else {
      filteredResults = window.scanResults.filter(r => {
        return window.Utils.wildmatch(filter, r.address) || window.Utils.wildmatch(filter, r.value);
      });
    }

    if (sortColumn) {
      doSort();
    }

    renderResultTable();
  }

  // 结果排序
  function sortResults(col) {
    if (sortColumn === col) {
      sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      sortColumn = col;
      sortDirection = 'asc';
    }

    doSort();
    renderResultTable();
  }

  function doSort() {
    filteredResults.sort((a, b) => {
      let valA = sortColumn === 'address' ? a.address : a.value;
      let valB = sortColumn === 'address' ? b.address : b.value;

      let numA = parseFloat(valA);
      let numB = parseFloat(valB);
      if (!isNaN(numA) && !isNaN(numB)) {
        return sortDirection === 'asc' ? numA - numB : numB - numA;
      }

      return sortDirection === 'asc'
        ? valA.localeCompare(valB)
        : valB.localeCompare(valA);
    });
  }

  function renderResultTable() {
    const thAddress = document.getElementById('th-address');
    const thValue = document.getElementById('th-value');

    if (thAddress) thAddress.classList.remove('sorted-asc', 'sorted-desc');
    if (thValue) thValue.classList.remove('sorted-asc', 'sorted-desc');

    if (sortColumn) {
      const th = document.getElementById(`th-${sortColumn}`);
      if (th) {
        th.classList.add(sortDirection === 'asc' ? 'sorted-asc' : 'sorted-desc');
      }
    }

    const tbody = document.querySelector('#resultTable tbody');
    if (!tbody) return;

    tbody.innerHTML = '';
    filteredResults.forEach((r, i) => {
      const row = tbody.insertRow();
      row.dataset.index = i;
      row.dataset.address = r.address;
      row.insertCell(0).textContent = r.address;
      row.insertCell(1).textContent = r.value;
      row.addEventListener('click', () => {
        document.querySelectorAll('#resultTable tbody tr').forEach(tr => tr.classList.remove('result-row-selected'));
        row.classList.add('result-row-selected');
        window.selectedAddress = r.address;
      });
    });

    window.Utils.showStatus('resultStatus', `显示 ${filteredResults.length} / ${window.scanResults.length} 条结果`);
  }

  async function refreshResults() {
    const data = await window.api.get('/api/results');
    if (data && data.results) {
      window.scanResults = data.results;
      filterResults();
      window.Utils.showStatus('resultStatus', '已刷新');
    }
  }

  // 修改与监视
  async function modifySelected() {
    if (!window.selectedAddress) { window.Utils.showStatus('modifyStatus', '请先选择地址'); return; }

    const modifyValue = document.getElementById('modifyValue');
    const newValue = modifyValue ? modifyValue.value : '';

    if (!newValue) { window.Utils.showStatus('modifyStatus', '请输入新值'); return; }

    const data = await window.api.post('/api/modify', { address: window.selectedAddress, value: newValue });
    if (data && data.status === 'ok') {
      window.Utils.showStatus('modifyStatus', '修改成功');
      refreshResults();
    } else {
      window.Utils.showStatus('modifyStatus', '修改失败');
    }
  }

  async function addToWatch() {
    if (!window.selectedAddress) { window.Utils.showStatus('modifyStatus', '请先选择地址'); return; }

    const data = await window.api.post('/api/watch', { address: window.selectedAddress });
    if (data && data.status === 'ok') {
      window.Utils.showStatus('modifyStatus', '已加入监视');
      window.TrackingPanel.updateWatchList();
    } else {
      window.Utils.showStatus('modifyStatus', '加入失败');
    }
  }

  // 内存查看器逻辑
  function autoFollowFirstScan() {
    if (window.scanResults && window.scanResults.length > 0) {
      document.getElementById('memStart').value = window.scanResults[0].address;
      // 同步类型
      const scanType = document.getElementById('scanType').value;
      document.getElementById('memType').value = scanType;
      refreshMemoryView();
    } else {
      window.Utils.showStatus('memStatus', '请先进行一次扫描，或者手动输入地址');
    }
  }

  async function refreshMemoryView() {
    if (!window.attached) { window.Utils.showStatus('memStatus', '未附加进程'); return; }

    const startStr = document.getElementById('memStart').value || '0x0';
    memType = parseInt(document.getElementById('memType').value);

    // 对齐地址
    try {
       memStartAddr = parseInt(startStr, 16);
    } catch(e) {
       memStartAddr = 0;
    }

    // 简单对齐
    const [, memTypeSize] = fill_scan_value_js("0", memType);

    window.Utils.showStatus('memStatus', '读取中...');

    const data = await window.api.post('/api/memory/view', {
      start: `0x${memStartAddr.toString(16)}`,
      count: MEM_VIEW_COUNT,
      type: memType
    });

    if (data && data.data) {
      memDataCache = data.data;
      memTypeSize = data.size;
      // 重置选择
      memSelectionStart = -1;
      memSelectionEnd = -1;
      updateMemSelectionCount();

      // 初始化 spacer
      const spacer = document.getElementById('memViewSpacer');
      if (spacer) spacer.style.height = `${memDataCache.length * MEM_ROW_HEIGHT}px`;

      renderMemView();
      window.Utils.showStatus('memStatus', `读取成功: ${memDataCache.length} 条`);
    } else {
      window.Utils.showStatus('memStatus', '读取失败');
    }
  }

  // JS端的简单大小计算，用于UI逻辑
  function fill_scan_value_js(dummy, typ) {
    switch(typ) {
      case 0: return [null, 1];
      case 1: return [null, 2];
      case 2: return [null, 4];
      case 3: return [null, 8];
      case 4: return [null, 4];
      case 5: return [null, 8];
      default: return [null, 4];
    }
  }

  function renderMemView() {
    const container = document.getElementById('memViewContainer');
    const content = document.getElementById('memViewContent');
    if (!container || !content) return;

    const scrollTop = container.scrollTop;
    const height = container.clientHeight;

    const startIdx = Math.floor(scrollTop / MEM_ROW_HEIGHT);
    // 多渲染一点防止白屏
    const endIdx = Math.min(memDataCache.length, startIdx + Math.ceil(height / MEM_ROW_HEIGHT) + 20);

    content.innerHTML = '';
    for (let i = startIdx; i < endIdx; i++) {
      const item = memDataCache[i];
      if (!item) continue;

      const isSelected = isIndexSelected(i);
      const key = item.address;
      const changed = memLastValues[key] && memLastValues[key] !== item.value;
      memLastValues[key] = item.value;

      const div = document.createElement('div');
      div.className = 'mem-row';
      div.dataset.idx = i;
      div.style.position = 'absolute';
      div.style.top = (i * MEM_ROW_HEIGHT) + 'px';
      div.style.height = MEM_ROW_HEIGHT + 'px';
      div.style.width = '100%';
      div.style.lineHeight = MEM_ROW_HEIGHT + 'px';
      div.style.display = 'flex';
      div.style.cursor = 'cell';
      div.style.userSelect = 'none';
      div.style.backgroundColor = isSelected ? '#094771' : (i % 2 === 0 ? '#252526' : '#1e1e1e');
      div.style.color = changed ? '#ffcc00' : '#d4d4d4';

      div.addEventListener('mousedown', (e) => startMemSelect(e, i));
      div.addEventListener('mouseenter', (e) => updateMemSelect(e, i));
      div.addEventListener('mouseup', endMemSelect);

      const addrSpan = document.createElement('span');
      addrSpan.style.width = '150px';
      addrSpan.style.padding = '0 10px';
      addrSpan.style.color = '#4fc1ff';
      addrSpan.textContent = item.address;

      const valSpan = document.createElement('span');
      valSpan.style.flex = '1';
      valSpan.style.padding = '0 10px';
      valSpan.style.fontWeight = changed ? 'bold' : 'normal';
      valSpan.textContent = item.value;

      div.appendChild(addrSpan);
      div.appendChild(valSpan);
      content.appendChild(div);
    }
  }

  function isIndexSelected(idx) {
    if (memSelectionStart === -1) return false;
    const min = Math.min(memSelectionStart, memSelectionEnd);
    const max = Math.max(memSelectionStart, memSelectionEnd);
    return idx >= min && idx <= max;
  }

  function startMemSelect(e, idx) {
    e.preventDefault();
    memIsSelecting = true;
    memSelectionStart = idx;
    memSelectionEnd = idx;
    updateMemSelectionCount();
    renderMemView();
  }

  function updateMemSelect(e, idx) {
    if (!memIsSelecting) return;
    if (memSelectionEnd !== idx) {
      memSelectionEnd = idx;
      updateMemSelectionCount();
      renderMemView();
    }
  }

  function endMemSelect(e) {
    memIsSelecting = false;
  }

  function clearMemorySelection() {
    memSelectionStart = -1;
    memSelectionEnd = -1;
    updateMemSelectionCount();
    renderMemView();
  }

  function updateMemSelectionCount() {
    let count = 0;
    if (memSelectionStart !== -1) {
      count = Math.abs(memSelectionEnd - memSelectionStart) + 1;
    }
    document.getElementById('selCount').textContent = count;
    document.getElementById('trackMemBtn').disabled = count === 0;
  }

  async function trackSelectedMemory() {
    if (memSelectionStart === -1) return;

    const min = Math.min(memSelectionStart, memSelectionEnd);
    const max = Math.max(memSelectionStart, memSelectionEnd);

    window.Utils.showStatus('memStatus', `正在添加 ${max - min + 1} 个追踪项...`);

    // 为了防止界面卡死，分批添加或者直接在前端构造列表发送给后端（这里简化为循环调用，或者只添加可视的）
    // 实际上最好是后端加一个批量API，这里演示直接循环调用前端逻辑
    let added = 0;

    // 临时保存当前 selectedAddress 以便恢复
    const oldSel = window.selectedAddress;

    for(let i = min; i <= max; i++) {
      const item = memDataCache[i];
      if(!item) continue;

      // 复用 addToTrack 逻辑
      window.selectedAddress = item.address;
      // 我们不真的一个个发请求，太卡了。
      // 我们直接把数据推到 trackList 并更新UI，最后统一发一个请求给后端（需要后端支持批量，这里简化为只更新UI并提示）

      // 这里为了演示稳定性，我们只取前 20 个加入，防止浏览器卡死
      if (added < 20) {
          const data = await window.api.post('/api/track/add', { address: item.address });
          if (data && data.status === 'ok') {
              window.trackList.push(item.address);
              added++;
          }
      }
    }

    window.selectedAddress = oldSel;
    window.Utils.showStatus('memStatus', `已添加 ${added} 个追踪项 (为防止性能问题，限制了数量)`);
    window.ProcessPanel.updateGlobalStatus();
  }

  // 查看内存区域
  async function showMemoryRegions() {
    if (!window.attached) {
      window.Utils.showStatus('processStatus', '请先附加进程');
      return;
    }
    const panel = document.getElementById('regionsPanel');
    const tbody = document.getElementById('regionsTableBody');
    if (panel) panel.style.display = 'block';
    if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="padding:10px;color:#666;text-align:center;">正在枚举内存区域...</td></tr>';
    
    const data = await window.api.get('/api/regions');
    if (!data || data.status !== 'ok') {
      if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="padding:10px;color:#dc3545;text-align:center;">枚举失败: ' + (data ? data.message : '未知错误') + '</td></tr>';
      return;
    }
    
    let html = '';
    for (const r of data.regions) {
      const sizeStr = r.size_mb > 0 ? r.size_mb + ' MB' : r.size + ' B';
      const typeColor = r.type === 'Private' ? '#28a745' : r.type === 'Mapped' ? '#fd7e14' : '#007bff';
      const stateColor = r.state === 'Commit' ? '#28a745' : '#999';
      html += '<tr style="border-bottom:1px solid #eee;">';
      html += '<td style="padding:4px 8px;font-family:monospace;">' + r.base_hex + '</td>';
      html += '<td style="padding:4px 8px;text-align:right;font-family:monospace;">' + sizeStr + '</td>';
      html += '<td style="padding:4px 8px;text-align:center;color:' + stateColor + '">' + r.state + '</td>';
      html += '<td style="padding:4px 8px;text-align:center;color:' + typeColor + '">' + r.type + '</td>';
      html += '<td style="padding:4px 8px;text-align:center;">' + r.protect + '</td>';
      html += '</tr>';
    }
    
    if (tbody) tbody.innerHTML = html;
  }

  // 导出到全局
  window.MemoryPanel = {
    init: initMemoryPanel,
    onScanModeChange: onScanModeChange,
    firstScan: firstScan,
    nextScan: nextScan,
    filterResults: filterResults,
    sortResults: sortResults,
    renderResultTable: renderResultTable,
    refreshResults: refreshResults,
    modifySelected: modifySelected,
    addToWatch: addToWatch,
    autoFollowFirstScan: autoFollowFirstScan,
    refreshMemoryView: refreshMemoryView,
    renderMemView: renderMemView,
    showMemoryRegions: showMemoryRegions,
    trackSelectedMemory: trackSelectedMemory,
    clearMemorySelection: clearMemorySelection,
  };
})();