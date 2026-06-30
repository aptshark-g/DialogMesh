// panels/process.js
(function() {
  'use strict';

  // 面板初始化
  function initProcessPanel() {
    const attachBtn = document.getElementById('attachBtn');
    if (attachBtn) attachBtn.addEventListener('click', attachSelected);

    const launchBtn = document.getElementById('launchBtn');
    if (launchBtn) launchBtn.addEventListener('click', launchTarget);

    const showAllBtn = document.getElementById('showAllBtn');
    if (showAllBtn) showAllBtn.addEventListener('click', showAllProcesses);

    const searchBtn = document.getElementById('searchBtn');
    if (searchBtn) searchBtn.addEventListener('click', searchProcesses);

    // 注意：updateGlobalStatus 轮询由 app.js 统一管理
  }

  // 全局状态更新
  async function updateGlobalStatus() {
    const data = await window.api.get('/api/status');
    if (!data) return;
    window.attached = data.attached;
    window.currentPid = data.pid;

    const globalStatusEl = document.getElementById('globalStatus');
    const attachedPidEl = document.getElementById('attachedPid');
    const attachBtn = document.getElementById('attachBtn');
    const modifyBtn = document.getElementById('modifyBtn');
    const addWatchBtn = document.getElementById('addWatchBtn');
    const addTrackBtn = document.getElementById('addTrackBtn');
    const startTrackBtn = document.getElementById('startTrackBtn');
    const taintBtn = document.getElementById('taintBtn');

    if (globalStatusEl) globalStatusEl.textContent = window.attached ? '已附加进程' : '未附加进程';
    if (attachedPidEl) attachedPidEl.textContent = window.attached ? `PID: ${window.currentPid}` : '';

    if (attachBtn) {
      // Never disable — allow switching to another process anytime
      attachBtn.textContent = window.attached ? '切换进程' : '附加进程';
      attachBtn.style.opacity = window.attached ? '0.8' : '1';
    }
    const regionsBtn = document.getElementById('regionsBtn');
    if (regionsBtn) regionsBtn.disabled = !window.attached;
    if (modifyBtn) modifyBtn.disabled = !window.attached;
    if (addWatchBtn) addWatchBtn.disabled = !window.attached;
    if (addTrackBtn) addTrackBtn.disabled = !window.attached;
    if (startTrackBtn) startTrackBtn.disabled = !window.attached || window.trackList.length === 0;
    if (taintBtn) taintBtn.disabled = !window.attached;
  }

  // 进程搜索
  async function searchProcesses() {
    try {
      const filterInput = document.getElementById('filterInput');
      const filter = filterInput ? filterInput.value : '';
      console.log('[searchProcesses] filter=' + filter);
      
      if (!window.api || !window.api.get) {
        console.error('[searchProcesses] window.api not available');
        window.Utils.showStatus('processStatus', '错误: API 未初始化，请刷新页面 (Ctrl+Shift+R)');
        return;
      }
      
      const data = await window.api.get('/api/processes?filter=' + encodeURIComponent(filter));
      console.log('[searchProcesses] data=', data);
      
      if (!data) {
        window.Utils.showStatus('processStatus', 'API 返回空数据');
        return;
      }
      if (data.error) {
        window.Utils.showStatus('processStatus', 'API 错误: ' + data.error);
        return;
      }

      const list = document.getElementById('processList');
      const processStatus = document.getElementById('processStatus');

      if (list) {
        list.innerHTML = '';
        data.forEach(p => {
          const item = document.createElement('div');
          item.className = 'process-list-item';
          item.dataset.pid = p.pid;
          item.onclick = () => selectProcessItem(item);

          const iconImg = document.createElement('img');
          iconImg.className = 'process-icon';
          iconImg.width = 16;
          iconImg.height = 16;
          if (p.icon_base64) {
            iconImg.src = 'data:image/png;base64,' + p.icon_base64;
          } else {
            iconImg.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16" fill="%23666"/></svg>';
          }

          const text = document.createElement('span');
          text.className = 'process-name';
          text.textContent = p.name || '(no name)';

          const pidLabel = document.createElement('span');
          pidLabel.className = 'process-pid';
          pidLabel.textContent = 'PID: ' + p.pid;

          item.appendChild(iconImg);
          item.appendChild(text);
          item.appendChild(pidLabel);
          list.appendChild(item);
        });
      }

      if (processStatus) {
        processStatus.textContent = '找到 ' + data.length + ' 个进程';
      }
    } catch (e) {
      console.error('[searchProcesses] error:', e);
      window.Utils.showStatus('processStatus', '错误: ' + e.message);
    }
  }

  function selectProcessItem(item) {
    const list = document.getElementById('processList');
    if (!list) return;
    list.querySelectorAll('.process-list-item').forEach(el => el.classList.remove('selected'));
    item.classList.add('selected');
  }

  function showAllProcesses() {
    const filterInput = document.getElementById('filterInput');
    if (filterInput) filterInput.value = '';
    searchProcesses();
  }

  async function attachSelected() {
    const list = document.getElementById('processList');
    if (!list) return;

    const sel = list.querySelector('.process-list-item.selected');
    if (!sel) {
      window.Utils.showStatus('processStatus', '请先选择进程');
      return;
    }

    const pid = parseInt(sel.dataset.pid);
    const data = await window.api.post('/api/attach', { pid });
    if (data && data.status === 'ok') {
      if (data.base_addr) {
        window.processBaseAddr = data.base_addr;
        console.log('[attachSelected] process base addr:', data.base_addr);
      }
      // Clear selection and refresh list to show new attach state
      list.querySelectorAll('.process-list-item').forEach(el => el.classList.remove('selected'));
      window.Utils.showStatus('processStatus', `已附加 PID ${pid}`);
      window.Utils.showStatus('globalStatus', '附加成功');
      await updateGlobalStatus();
      // 附加成功后自动加载内存区域信息
      if (window.MemoryPanel && window.MemoryPanel.showMemoryRegions) {
        await window.MemoryPanel.showMemoryRegions();
      }
    } else {
      window.Utils.showStatus('globalStatus', '附加失败: ' + (data?.message || '未知错误'));
    }
  }

  // 启动靶机并自动附加
  async function launchTarget() {
    const exePath = document.getElementById('launchExePath').value.trim();
    const args = document.getElementById('launchArgs').value.trim();
    if (!exePath) {
      window.Utils.showStatus('processStatus', '请输入程序路径');
      return;
    }
    window.Utils.showStatus('processStatus', '正在启动...');
    const data = await window.api.post('/api/launch', {
      exe_path: exePath,
      args: args,
    });
    if (data && data.status === 'ok') {
      if (data.base_addr) {
        window.processBaseAddr = data.base_addr;
        console.log('[launchTarget] process base addr:', data.base_addr);
      }
      window.Utils.showStatus('processStatus', `启动成功 PID=${data.pid}`);
      window.Utils.showStatus('globalStatus', '已附加启动的进程');
      await updateGlobalStatus();
      // 刷新进程列表以显示新进程
      await searchProcesses();
    } else {
      window.Utils.showStatus('processStatus', '启动失败: ' + (data ? data.message : '未知错误'));
    }
  }

  // 导出到全局
  window.ProcessPanel = {
    init: initProcessPanel,
    updateGlobalStatus: updateGlobalStatus,
    searchProcesses: searchProcesses,
    showAllProcesses: showAllProcesses,
    attachSelected: attachSelected,
    launchTarget: launchTarget,
  };
})();