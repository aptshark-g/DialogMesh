import { Globe, Database } from 'lucide-react';
import { motion } from 'framer-motion';
import { ApiConfigPanel } from '../components/ApiConfigPanel';

export function SettingsPage() {
  const handleClearCache = () => {
    const keys = Object.keys(localStorage).filter((k) => k.startsWith('dialogmesh_'));
    keys.forEach((k) => localStorage.removeItem(k));
    console.log('Cleared localStorage keys:', keys);
    alert('本地缓存已清除');
  };

  return (
    <div className="h-full flex flex-col max-w-5xl mx-auto">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-text-primary">设置</h1>
        <p className="text-sm text-text-secondary mt-1">
          配置 DialogMesh 前端连接参数
        </p>
      </div>

      <div className="space-y-4">
        <ApiConfigPanel />

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.2 }}
          className="bg-surface-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6"
        >
          <div className="flex items-center gap-3 mb-4">
            <Globe className="w-5 h-5 text-primary" />
            <h2 className="text-base font-semibold text-text-primary">界面</h2>
          </div>
          <div className="text-sm text-text-secondary">
            界面语言已固定为中文。技术术语（如 Session、WebSocket、FSM）保持英文。
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.3 }}
          className="bg-surface-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6"
        >
          <div className="flex items-center gap-3 mb-4">
            <Database className="w-5 h-5 text-primary" />
            <h2 className="text-base font-semibold text-text-primary">缓存</h2>
          </div>
          <button
            type="button"
            onClick={handleClearCache}
            className={[
              'px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700',
              'text-sm text-text-secondary hover:bg-gray-50 dark:hover:bg-gray-800',
              'transition-colors',
            ].join(' ')}
          >
            清除本地缓存
          </button>
        </motion.div>
      </div>
    </div>
  );
}
