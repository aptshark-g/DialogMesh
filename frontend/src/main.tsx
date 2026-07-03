import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';

// 检测是否在浏览器扩展环境中运行
const extWindow = window as unknown as { chrome?: { runtime?: { id?: string } } };
const isExtension = typeof extWindow.chrome !== 'undefined' && extWindow.chrome?.runtime?.id;

if (isExtension) {
  document.documentElement.classList.add('extension-mode');
  console.log('[DialogMesh] Extension mode active');
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
