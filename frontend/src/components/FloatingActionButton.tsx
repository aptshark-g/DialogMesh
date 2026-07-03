import { motion, AnimatePresence } from 'framer-motion';
import { MessageSquare, X } from 'lucide-react';
import { useOverlayStore } from '@/stores/overlayStore';
import { ChatOverlay } from './ChatOverlay';
import { cn } from '@/lib/utils';

export function FloatingActionButton() {
  const { isOpen, toggle, unreadCount, badgeVisible } = useOverlayStore();

  return (
    <div className="fixed bottom-6 right-6 z-[500] flex flex-col items-end gap-3">
      <AnimatePresence>
        {isOpen && (
          <motion.div
            key="overlay"
            initial={{ opacity: 0, y: 20, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.9 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          >
            <ChatOverlay />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="relative">
        <motion.button
          type="button"
          onClick={toggle}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className={cn(
            'w-14 h-14 rounded-full shadow-lg flex items-center justify-center transition-colors',
            isOpen
              ? 'bg-rose hover:bg-[#BE123C] text-white'
              : 'bg-primary hover:bg-primary-dark text-white'
          )}
          aria-label={isOpen ? '关闭聊天' : '打开聊天'}
        >
          <AnimatePresence mode="wait">
            {isOpen ? (
              <motion.div
                key="close"
                initial={{ rotate: -90, opacity: 0 }}
                animate={{ rotate: 0, opacity: 1 }}
                exit={{ rotate: 90, opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <X className="w-6 h-6" />
              </motion.div>
            ) : (
              <motion.div
                key="chat"
                initial={{ rotate: 90, opacity: 0 }}
                animate={{ rotate: 0, opacity: 1 }}
                exit={{ rotate: -90, opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <MessageSquare className="w-6 h-6" />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.button>

        <AnimatePresence>
          {badgeVisible && unreadCount > 0 && !isOpen && (
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0 }}
              className="absolute -top-2 -right-2 min-w-[22px] h-[22px] rounded-full bg-rose text-white text-xs font-bold flex items-center justify-center px-1.5"
            >
              {unreadCount > 9 ? '9+' : unreadCount}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
