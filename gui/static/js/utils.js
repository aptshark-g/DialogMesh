// gui/static/js/utils.js — 通用工具函数

function showStatus(elementId, text) {
  const el = document.getElementById(elementId);
  if (el) el.textContent = text;
}

function wildmatch(pattern, text) {
  const regex = new RegExp(
    '^' + pattern.replace(/\\\\/g, '\\\\')
                  .replace(/\\\*/g, '.*')
                  .replace(/\\\?/g, '.') + '$',
    'i'
  );
  return regex.test(text);
}

function formatValue(val, type) {
  if (val === null || val === undefined) return '?';
  switch (type) {
    case 0: return val.toString();
    case 1: return val.toString();
    case 2: return val.toString();
    case 3: return val.toString();
    case 4: return parseFloat(val).toFixed(6);
    case 5: return parseFloat(val).toFixed(15);
    default: return String(val);
  }
}

function formatAddress(addr) {
  if (typeof addr === 'number') {
    return '0x' + addr.toString(16).toUpperCase().padStart(8, '0');
  }
  if (typeof addr === 'string' && addr.startsWith('0x')) return addr;
  return '0x' + parseInt(addr).toString(16);
}

function debounce(fn, ms) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), ms);
  };
}

function showToast(msg, type = 'info') {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.style.cssText = `
    margin-bottom:8px;padding:12px 20px;border-radius:4px;color:#fff;font-size:14px;
    background:${type === 'success' ? '#28a745' : type === 'error' ? '#dc3545' : type === 'warning' ? '#ffc107' : '#007bff'};
    box-shadow:0 2px 8px rgba(0,0,0,0.3);transition:opacity 0.3s;
  `;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function copyToClipboard(text) {
  return navigator.clipboard.writeText(text).then(() => true).catch(() => false);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function parseHexOrDec(str) {
  if (!str) return NaN;
  str = str.trim();
  if (str.startsWith('0x') || str.startsWith('0X')) return parseInt(str, 16);
  return parseInt(str, 10);
}

function fill_scan_value_js(dummy, typ) {
  switch (typ) {
    case 0: return [null, 1];
    case 1: return [null, 2];
    case 2: return [null, 4];
    case 3: return [null, 8];
    case 4: return [null, 4];
    case 5: return [null, 8];
    default: return [null, 4];
  }
}

// 导出到全局 Utils 对象
window.Utils = {
  showStatus: showStatus,
  wildmatch: wildmatch,
  formatValue: formatValue,
  formatAddress: formatAddress,
  debounce: debounce,
  showToast: showToast,
  copyToClipboard: copyToClipboard,
  escapeHtml: escapeHtml,
  parseHexOrDec: parseHexOrDec,
  fill_scan_value_js: fill_scan_value_js
};
