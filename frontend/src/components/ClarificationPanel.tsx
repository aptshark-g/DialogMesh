// FILE: frontend/src/components/ClarificationPanel.tsx

import { useState } from 'react';
import { cn } from '../lib/utils';
import type { ClarificationItem } from '../types/api';
import { HelpCircle, Send } from 'lucide-react';

interface ClarificationPanelProps {
  items: ClarificationItem[];
  onSubmit: (answers: Record<string, string>) => void;
  className?: string;
}

export function ClarificationPanel({ items, onSubmit, className }: ClarificationPanelProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, boolean>>({});

  const handleSubmit = () => {
    const newErrors: Record<string, boolean> = {};
    let hasError = false;

    for (const item of items) {
      if (item.required && !answers[item.field]?.trim()) {
        newErrors[item.field] = true;
        hasError = true;
      }
    }

    if (hasError) {
      setErrors(newErrors);
      return;
    }

    setErrors({});
    onSubmit(answers);
  };

  return (
    <div className={cn('rounded-xl bg-status-warning/5 border border-status-warning/20 overflow-hidden', className)}>
      <div className="px-4 py-3 border-b border-status-warning/10 flex items-center gap-2">
        <HelpCircle className="h-4 w-4 text-status-warning" />
        <span className="text-sm font-medium text-text-primary">需要澄清</span>
      </div>

      <div className="px-4 py-3 space-y-4">
        {items.map((item) => (
          <div key={item.field}>
            <label className="block text-sm font-medium text-text-primary mb-1.5">
              {item.question}
              {item.required && <span className="text-status-error ml-1">*</span>}
            </label>

            {item.options && item.options.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {item.options.map((opt: string) => (
                  <button
                    key={opt}
                    onClick={() =>
                      setAnswers((prev) => ({ ...prev, [item.field]: opt }))
                    }
                    className={cn(
                      'px-3 py-1.5 rounded-lg text-sm border transition-colors',
                      answers[item.field] === opt
                        ? 'bg-primary text-white border-primary'
                        : 'bg-white text-text-primary border-gray-200 hover:border-primary/50'
                    )}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            ) : (
              <input
                type="text"
                value={answers[item.field] || ''}
                onChange={(e) =>
                  setAnswers((prev) => ({ ...prev, [item.field]: e.target.value }))
                }
                placeholder="请输入..."
                className={cn(
                  'w-full px-3 py-2 rounded-lg border text-sm outline-none transition-colors',
                  errors[item.field]
                    ? 'border-status-error focus:border-status-error focus:ring-1 focus:ring-status-error/20'
                    : 'border-gray-200 focus:border-primary focus:ring-1 focus:ring-primary/20'
                )}
              />
            )}
            {errors[item.field] && (
              <p className="text-xs text-status-error mt-1">此项为必填</p>
            )}
          </div>
        ))}

        <button
          onClick={handleSubmit}
          className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary text-white px-4 py-2.5 text-sm font-medium hover:bg-primary-dark transition-colors"
        >
          <Send className="h-4 w-4" />
          提交澄清
        </button>
      </div>
    </div>
  );
}
