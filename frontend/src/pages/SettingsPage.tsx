import { Server, Globe, Database } from 'lucide-react';

export function SettingsPage() {
  return (
    <div className="h-full flex flex-col max-w-5xl mx-auto">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-text-primary">设置</h1>
        <p className="text-sm text-text-secondary mt-1">
          配置 DialogMesh 前端连接参数
        </p>
      </div>

      <div className="space-y-4">
        <div className="bg-surface-card rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex items-center gap-3 mb-4">
            <Server className="w-5 h-5 text-primary" />
            <h2 className="text-base font-semibold text-text-primary">后端连接</h2>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1">
                REST API Base URL
              </label>
              <input
                type="text"
                defaultValue="http://localhost:8000"
                className={[
                  'w-full px-4 py-2 rounded-lg border border-gray-200',
                  'bg-surface-main text-text-primary text-sm',
                  'focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary',
                ].join(' ')}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1">
                WebSocket Base URL
              </label>
              <input
                type="text"
                defaultValue="ws://localhost:8000"
                className={[
                  'w-full px-4 py-2 rounded-lg border border-gray-200',
                  'bg-surface-main text-text-primary text-sm',
                  'focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary',
                ].join(' ')}
              />
            </div>
          </div>
        </div>

        <div className="bg-surface-card rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex items-center gap-3 mb-4">
            <Globe className="w-5 h-5 text-primary" />
            <h2 className="text-base font-semibold text-text-primary">界面</h2>
          </div>
          <div className="text-sm text-text-secondary">
            界面语言已固定为中文。技术术语（如 Session、WebSocket、FSM）保持英文。
          </div>
        </div>

        <div className="bg-surface-card rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex items-center gap-3 mb-4">
            <Database className="w-5 h-5 text-primary" />
            <h2 className="text-base font-semibold text-text-primary">缓存</h2>
          </div>
          <button
            type="button"
            className={[
              'px-4 py-2 rounded-lg border border-gray-200',
              'text-sm text-text-secondary hover:bg-gray-50',
              'transition-colors',
            ].join(' ')}
          >
            清除本地缓存
          </button>
        </div>
      </div>
    </div>
  );
}
