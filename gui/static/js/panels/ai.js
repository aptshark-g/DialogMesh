// panels/ai.js
(function() {
  'use strict';

  async function aiGenerateProjectPrompt() {
    const context = document.getElementById('aiProjectContext').value;
    document.getElementById('aiPromptOutput').textContent = '正在收集项目文件并生成协同分析 Prompt...';
    try {
      const r = await fetch(`${window.BASE || ''}/api/ai/generate-project`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context: context, max_files: 10 })
      });
      const j = await r.json();
      if (j.status === 'ok') {
        document.getElementById('aiPromptOutput').textContent = j.prompt;
      } else {
        document.getElementById('aiPromptOutput').textContent = '错误: ' + j.message;
      }
    } catch (e) { document.getElementById('aiPromptOutput').textContent = '请求失败: ' + e; }
  }

  async function aiGeneratePrompt(type) {
    const code = document.getElementById('aiCodeInput').value;
    const lang = document.getElementById('aiLang').value;
    const context = document.getElementById('aiContext').value;
    if (!code) { alert('请输入代码'); return; }
    document.getElementById('aiPromptOutput').textContent = '生成 Prompt 中...';
    try {
      const r = await fetch(`${window.BASE || ''}/api/ai/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: type, code: code, language: lang, context: context, error: document.getElementById('aiErrorDesc').value })
      });
      const j = await r.json();
      if (j.status === 'ok') {
        document.getElementById('aiPromptOutput').textContent = j.prompt;
      } else {
        document.getElementById('aiPromptOutput').textContent = '错误: ' + j.message;
      }
    } catch (e) { document.getElementById('aiPromptOutput').textContent = '请求失败: ' + e; }
  }

  async function aiGenerateReversePrompt() {
    document.getElementById('aiReversePromptOutput').textContent = '生成逆向 Prompt 中...';
    try {
      const r = await fetch(`${window.BASE || ''}/api/ai/generate-reverse`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
      const j = await r.json();
      if (j.status === 'ok') {
        document.getElementById('aiReversePromptOutput').textContent = j.prompt;
      } else {
        document.getElementById('aiReversePromptOutput').textContent = '错误: ' + j.message;
      }
    } catch (e) { document.getElementById('aiReversePromptOutput').textContent = '请求失败: ' + e; }
  }

  function copyToClipboard(elementId) {
    const text = document.getElementById(elementId).textContent;
    navigator.clipboard.writeText(text).then(() => {
      document.getElementById('aiCopyStatus').textContent = '已复制！';
      setTimeout(() => document.getElementById('aiCopyStatus').textContent = '', 2000);
    }).catch(() => {
      document.getElementById('aiCopyStatus').textContent = '复制失败';
    });
  }

  async function loadProviderStatus() {
    try {
      const r = await fetch(`${window.BASE || ''}/api/providers`);
      const j = await r.json();
      if (j.status === 'ok') {
        const select = document.getElementById('aiProvider');
        j.providers.forEach(p => {
          const option = select.querySelector(`option[value="${p.name}"]`);
          if (option) {
            option.textContent = `${p.display_name} ${p.available ? '(可用)' : '(未配置)'}`;
          }
        });

        select.value = j.active_provider;

        const active = j.providers.find(p => p.active);
        if (active) {
          document.getElementById('providerStatus').textContent = 
            `当前: ${active.display_name} ${active.available ? '可用' : '未配置'}`;
        }
      }
    } catch (e) {
      document.getElementById('providerStatus').textContent = '检测失败';
    }
  }

  async function setProvider() {
    const provider = document.getElementById('aiProvider').value;
    try {
      const r = await fetch(`${window.BASE || ''}/api/providers/${provider}/set`, { method: 'POST' });
      const j = await r.json();
      if (j.status === 'ok') {
        document.getElementById('providerStatus').textContent = `已切换为 ${provider}`;
        document.getElementById('providerStatus').style.color = '#28a745';
        loadProviderStatus();
      } else {
        document.getElementById('providerStatus').textContent = `切换失败: ${j.message}`;
        document.getElementById('providerStatus').style.color = '#dc3545';
      }
    } catch (e) {
      document.getElementById('providerStatus').textContent = `请求失败: ${e}`;
      document.getElementById('providerStatus').style.color = '#dc3545';
    }
  }

  function initAIPanel() {
    window.addEventListener('load', loadProviderStatus);
  }

  window.AIPanel = {
    init: initAIPanel,
    generateProjectPrompt: aiGenerateProjectPrompt,
    generatePrompt: aiGeneratePrompt,
    generateReversePrompt: aiGenerateReversePrompt,
    copyToClipboard: copyToClipboard,
    loadProviderStatus: loadProviderStatus,
    setProvider: setProvider,
  };
})();
