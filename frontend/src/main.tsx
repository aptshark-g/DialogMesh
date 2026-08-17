import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import './light.css';
import './dark.css';
import App from './App.tsx';

// 检测是否在浏览器扩展环境中运行
const extWindow = window as unknown as { chrome?: { runtime?: { id?: string } } };
const isExtension = typeof extWindow.chrome !== 'undefined' && extWindow.chrome?.runtime?.id;

if (isExtension) {
  document.documentElement.classList.add('extension-mode');
  console.log('[DialogMesh] Extension mode active');
}

// P1-M: card-liquid 全局指针追光委托 — 单监听器覆盖现有/未来全部液体卡片,
// 每事件仅写 2 个 CSS 变量(小面积重绘, 无 layout); 显隐由 :hover 伪类托管
window.addEventListener('pointermove', (e) => {
  const el = (e.target as Element | null)?.closest?.('.card-liquid');
  if (el instanceof HTMLElement) {
    const r = el.getBoundingClientRect();
    el.style.setProperty('--mx', `${e.clientX - r.left}px`);
    el.style.setProperty('--my', `${e.clientY - r.top}px`);
  }
}, { passive: true });

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
