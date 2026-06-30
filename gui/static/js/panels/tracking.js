// panels/tracking.js
(function() {
  'use strict';

  // 面板初始化
  function initTrackingPanel() {
    const addTrackBtn = document.getElementById('addTrackBtn');
    if (addTrackBtn) addTrackBtn.addEventListener('click', addToTrack);

    const startTrackBtn = document.getElementById('startTrackBtn');
    if (startTrackBtn) startTrackBtn.addEventListener('click', startTrack);

    const stopTrackBtn = document.getElementById('stopTrackBtn');
    if (stopTrackBtn) stopTrackBtn.addEventListener('click', stopTrack);

    const taintBtn = document.getElementById('taintBtn');
    if (taintBtn) taintBtn.addEventListener('click', injectTaint);

    const removeWatchBtn = document.getElementById('removeWatchBtn');
    if (removeWatchBtn) removeWatchBtn.addEventListener('click', removeWatchItem);

    // 注意：updateWatchList 轮询由 app.js 统一管理
  }

  // 观察列表
  async function updateWatchList() {
    const data = await window.api.get('/api/watch');
    if (!data) return;

    window.watchList = data.watch || [];
    const tbody = document.querySelector('#watchTable tbody');
    const removeWatchBtn = document.getElementById('removeWatchBtn');

    if (tbody) {
      tbody.innerHTML = '';
      window.watchList.forEach((w, i) => {
        const row = tbody.insertRow();
        row.dataset.index = i;
        row.insertCell(0).textContent = w.address;
        const valCell = row.insertCell(1);
        valCell.innerHTML = w.changed ? `<span class="changed">${w.value} *</span>` : w.value;
        row.addEventListener('click', () => {
          document.querySelectorAll('#watchTable tbody tr').forEach(tr => tr.classList.remove('result-row-selected'));
          row.classList.add('result-row-selected');
        });
      });
    }

    if (removeWatchBtn) {
      removeWatchBtn.disabled = window.watchList.length === 0;
    }
  }

  async function removeWatchItem() {
    const row = document.querySelector('#watchTable tbody tr.result-row-selected');
    if (!row) { window.Utils.showStatus('watchStatus', '请先选择要移除的项'); return; }

    const idx = parseInt(row.dataset.index);
    const data = await window.api.post('/api/watch/remove', { index: idx });
    if (data && data.status === 'ok') {
      window.Utils.showStatus('watchStatus', '已移除');
      updateWatchList();
    }
  }

  // 时序追踪功能
  async function addToTrack() {
    if (!window.selectedAddress) { window.Utils.showStatus('modifyStatus', '请先选择地址'); return; }

    const data = await window.api.post('/api/track/add', { address: window.selectedAddress });
    if (data && data.status === 'ok') {
      window.trackList.push(window.selectedAddress);
      window.Utils.showStatus('trackStatus', `追踪地址数: ${data.count}`);
      window.Utils.showStatus('modifyStatus', '已加入时序追踪');
      window.ProcessPanel.updateGlobalStatus();
    }
  }

  async function startTrack() {
    const data = await window.api.post('/api/track/start', {});
    if (data && data.status === 'ok') {
      window.Utils.showStatus('trackStatus', '正在追踪中...（请操作目标程序）');
      const startTrackBtn = document.getElementById('startTrackBtn');
      const stopTrackBtn = document.getElementById('stopTrackBtn');
      if (startTrackBtn) startTrackBtn.disabled = true;
      if (stopTrackBtn) stopTrackBtn.disabled = false;
    }
  }

  async function stopTrack() {
    const data = await window.api.post('/api/track/stop', {});
    if (!data) return;

    const startTrackBtn = document.getElementById('startTrackBtn');
    const stopTrackBtn = document.getElementById('stopTrackBtn');
    if (startTrackBtn) startTrackBtn.disabled = false;
    if (stopTrackBtn) stopTrackBtn.disabled = true;

    window.Utils.showStatus('trackStatus', `分析完成，找到 ${data.edges.length} 条依赖关系`);

    renderTimelineChart(data.nodes);
    renderDependencyChart(data.nodes, data.edges);
    renderCategoryTable(data.nodes);
  }

  async function injectTaint() {
    if (!window.selectedAddress) { window.Utils.showStatus('trackStatus', '请先选择地址'); return; }

    const taintValue = document.getElementById('taintValue');
    const value = taintValue ? taintValue.value : '';

    if (!value) { window.Utils.showStatus('trackStatus', '请输入注入值'); return; }

    const data = await window.api.post('/api/track/taint', { address: window.selectedAddress, value: value });
    if (data && data.status === 'ok') {
      window.Utils.showStatus('trackStatus', '污点注入成功！继续操作目标程序...');
    } else {
      window.Utils.showStatus('trackStatus', '注入失败');
    }
  }

  // 图表渲染
  function renderTimelineChart(nodes) {
    const chartDom = document.getElementById('timelineChart');
    if (!chartDom) return;

    const chart = echarts.init(chartDom);
    const series = nodes.map(node => {
      const data = node.timestamps.map((ts, i) => [ts, node.values[i]]);
      return {
        name: node.address,
        type: 'line',
        data: data,
        symbol: 'none',
        lineStyle: { width: 2 }
      };
    });

    chart.setOption({
      title: { text: '内存时序数据' },
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'value', name: '时间(ms)' },
      yAxis: { type: 'value', name: '数值' },
      series: series,
      dataZoom: [{ type: 'inside', xAxisIndex: 0, start: 0, end: 100 }]
    });

    window.addEventListener('resize', () => chart.resize());
  }

  function renderDependencyChart(nodes, edges) {
    const chartDom = document.getElementById('dependencyChart');
    if (!chartDom) return;

    const chart = echarts.init(chartDom);
    const categoryColor = {
      'constant': '#666666',
      'cyclic': '#0078d4',
      'interactive': '#28a745',
      'noise': '#dc3545',
      'unknown': '#999999'
    };

    const chartNodes = nodes.map(node => ({
      id: node.id,
      name: node.address,
      category: node.category,
      itemStyle: { color: categoryColor[node.category] || '#999' },
      symbolSize: 20
    }));

    const chartLinks = edges.map(edge => ({
      source: edge.source,
      target: edge.target,
      value: edge.correlation,
      lineStyle: {
        width: Math.abs(edge.correlation) * 5,
        curveness: 0.2,
        type: edge.delay > 0 ? 'solid' : 'dashed'
      },
      label: {
        show: true,
        formatter: `r: ${edge.correlation.toFixed(2)}\nΔt: ${edge.delay}ms`
      }
    }));

    const categories = Object.keys(categoryColor).map(c => ({ name: c }));

    chart.setOption({
      title: { text: '数据依赖关联图（实线=因果，虚线=相关）' },
      tooltip: {
        formatter: function(params) {
          if (params.dataType === 'edge') {
            return `${params.data.sourceName} → ${params.data.targetName}<br/>相关系数: ${params.data.value.toFixed(4)}<br/>延迟: ${params.data.delay}ms`;
          }
          return params.name;
        }
      },
      legend: [{ data: categories.map(c => c.name) }],
      series: [{
        type: 'graph',
        layout: 'force',
        data: chartNodes,
        links: chartLinks,
        categories: categories,
        roam: true,
        label: { show: true, position: 'right' },
        lineStyle: { color: 'source', opacity: 0.6 },
        emphasis: { focus: 'adjacency', lineStyle: { width: 10 } },
        force: { repulsion: 500, edgeLength: 150 }
      }]
    });

    window.addEventListener('resize', () => chart.resize());
  }

  function renderCategoryTable(nodes) {
    const tbody = document.querySelector('#categoryTable tbody');
    if (!tbody) return;

    tbody.innerHTML = '';
    nodes.forEach(node => {
      const row = tbody.insertRow();
      row.insertCell(0).textContent = node.address;
      const catCell = row.insertCell(1);
      catCell.textContent = node.category;
      catCell.className = `category-${node.category}`;
      row.insertCell(2).textContent = node.timestamps.length;
      row.insertCell(3).textContent = JSON.stringify(node.features || {});
    });
  }

  // 导出到全局
  window.TrackingPanel = {
    init: initTrackingPanel,
    updateWatchList: updateWatchList,
    removeWatchItem: removeWatchItem,
    addToTrack: addToTrack,
    startTrack: startTrack,
    stopTrack: stopTrack,
    injectTaint: injectTaint,
    renderTimelineChart: renderTimelineChart,
    renderDependencyChart: renderDependencyChart,
    renderCategoryTable: renderCategoryTable,
  };
})();