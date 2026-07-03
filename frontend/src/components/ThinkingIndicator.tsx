import { memo } from 'react';
import { Brain, CheckCircle2 } from 'lucide-react';
import { motion } from 'framer-motion';
import type { ThinkingStep } from '../types/api';

interface ThinkingIndicatorProps {
  steps: ThinkingStep[];
}

const ThinkingIndicator = memo(function ThinkingIndicator({ steps }: ThinkingIndicatorProps) {
  return (
    <div className="flex w-full mb-4 justify-start">
      <div className="flex max-w-[92%] sm:max-w-[85%] md:max-w-[75%] gap-2 md:gap-3 flex-row">
        <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-surface-thinking text-primary">
          <Brain size={16} className="animate-pulse" />
        </div>
        <div className="flex flex-col items-start">
          <div className="px-4 py-3 rounded-2xl rounded-bl-md bg-surface-thinking border border-primary-light/50 text-sm text-text-primary shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-primary font-medium text-xs">AI 思考中</span>
              <div className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <motion.div
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-primary"
                    animate={{
                      scale: [0, 1, 0],
                      opacity: [0, 1, 0],
                    }}
                    transition={{
                      duration: 1.4,
                      repeat: Infinity,
                      delay: i * 0.16,
                      ease: 'easeInOut',
                    }}
                  />
                ))}
              </div>
            </div>
            {steps.length > 0 && (
              <div className="space-y-1.5">
                {steps.map((s, idx) => (
                  <motion.div
                    key={idx}
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.08 }}
                    className="flex items-start gap-2 text-xs"
                  >
                    <CheckCircle2 size={14} className="text-primary mt-0.5 flex-shrink-0" />
                    <span className="text-text-secondary">{s.description}</span>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
});

export default ThinkingIndicator;
