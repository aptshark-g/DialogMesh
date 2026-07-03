import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { cn } from '@/lib/utils';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface ToastProps {
  type?: ToastType;
  message: string;
  title?: string;
  onClose?: () => void;
  duration?: number;
}

const typeConfig: Record<
  ToastType,
  { border: string; icon: React.ReactNode }
> = {
  success: {
    border: 'border-[#10B981]',
    icon: <CheckCircle className="h-5 w-5 text-[#10B981]" />,
  },
  error: {
    border: 'border-[#EF4444]',
    icon: <AlertCircle className="h-5 w-5 text-[#EF4444]" />,
  },
  warning: {
    border: 'border-[#F59E0B]',
    icon: <AlertTriangle className="h-5 w-5 text-[#F59E0B]" />,
  },
  info: {
    border: 'border-[#3B82F6]',
    icon: <Info className="h-5 w-5 text-[#3B82F6]" />,
  },
};

const Toast: React.FC<ToastProps> = ({
  type = 'info',
  message,
  title,
  onClose,
  duration = 3000,
}) => {
  const [isVisible, setIsVisible] = useState(true);
  const config = typeConfig[type];

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVisible(false);
    }, duration);
    return () => clearTimeout(timer);
  }, [duration]);

  const handleExit = () => {
    onClose?.();
  };

  return (
    <AnimatePresence onExitComplete={handleExit}>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, x: 100, scale: 0.95 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          exit={{ opacity: 0, x: 100, scale: 0.95 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          className={cn(
            'fixed top-4 right-4 z-[100] min-w-[320px] max-w-[400px]',
            'bg-surface-card border-l-4 rounded-md shadow-card-hover',
            'p-4 flex gap-3',
            config.border
          )}
        >
          <div className="flex-shrink-0 mt-0.5">{config.icon}</div>
          <div className="flex-1 min-w-0">
            {title && (
              <p className="text-sm font-semibold text-[#E8E6F0] mb-1">
                {title}
              </p>
            )}
            <p className="text-sm text-[#A9A5B8]">{message}</p>
          </div>
          <button
            onClick={() => setIsVisible(false)}
            className="flex-shrink-0 text-[#6B6680] hover:text-[#E8E6F0] transition-colors"
            aria-label="Close toast"
          >
            <X className="h-4 w-4" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export { Toast };
export type { ToastProps };
