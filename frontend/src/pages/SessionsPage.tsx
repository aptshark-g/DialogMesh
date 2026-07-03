import { Plus, Clock, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';

export function SessionsPage() {
  const navigate = useNavigate();

  return (
    <div className="h-full flex flex-col max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Session 管理</h1>
          <p className="text-sm text-text-secondary mt-1">
            查看和管理活跃的对话 Session
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            console.log('新建 Session');
            navigate('/chat');
          }}
          className={[
            'px-4 py-2 rounded-lg bg-primary text-white',
            'text-sm font-medium hover:bg-primary-dark',
            'transition-colors flex items-center gap-2',
          ].join(' ')}
        >
          <Plus className="w-4 h-4" />
          新建 Session
        </button>
      </div>

      <div className="bg-surface-card rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="divide-y divide-gray-100">
          {[1, 2, 3].map((i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: i * 0.1 }}
              className={[
                'flex items-center justify-between px-6 py-4',
                'hover:bg-surface-main transition-colors cursor-pointer group',
              ].join(' ')}
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Clock className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    Session-{i}
                  </p>
                  <p className="text-xs text-text-muted mt-0.5">
                    2 分钟前 · 3 turns
                  </p>
                </div>
              </div>
              <ArrowRight className="w-4 h-4 text-text-muted group-hover:text-primary transition-colors" />
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
