// FILE: frontend/src/components/sessions/IngestDocumentModal.tsx
// 文档导入 Modal — 文件选择 / 文本输入 → /v4/ingest

import { useRef, useState } from 'react';
import { AlertCircle, FileText, Upload } from 'lucide-react';
import { ingestDocument } from '../../api/v4';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';

interface IngestDocumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (message: string) => void;
}

const FILE_TYPES = [
  { value: 'markdown', label: 'Markdown' },
  { value: 'text', label: 'Plain Text' },
  { value: 'json', label: 'JSON' },
] as const;

export function IngestDocumentModal({
  isOpen,
  onClose,
  onSuccess,
}: IngestDocumentModalProps) {
  const [sourcePath, setSourcePath] = useState('');
  const [content, setContent] = useState('');
  const [fileType, setFileType] = useState<string>('markdown');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setSourcePath('');
    setContent('');
    setFileType('markdown');
    setError(null);
    setSubmitting(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSourcePath(file.name);
    if (/\.json$/i.test(file.name)) setFileType('json');
    else if (/\.(txt|text|log)$/i.test(file.name)) setFileType('text');
    else setFileType('markdown');
    try {
      setContent(await file.text());
      setError(null);
    } catch {
      setError('读取文件失败,请改用文本粘贴');
    }
  };

  const handleSubmit = async () => {
    const path = sourcePath.trim();
    if (!path) {
      setError('请填写来源路径(source_path)');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const resp = await ingestDocument(
        path,
        content.trim() || undefined,
        fileType
      );
      onSuccess(
        `已导入 ${resp.source_path},生成 ${resp.observation_count} 条观察`
      );
      reset();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '导入失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="导入文档"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={handleClose} disabled={submitting}>
            取消
          </Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            loading={submitting}
            disabled={!sourcePath.trim()}
          >
            导入
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {/* 文件选择 */}
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1.5">
            选择文件
          </label>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 px-4 py-6 rounded-lg border border-dashed border-border-medium hover:border-primary hover:bg-primary/5 text-text-secondary hover:text-primary transition-colors text-sm"
          >
            <Upload className="h-4 w-4" />
            点击选择本地文件(.md / .txt / .json)
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".md,.markdown,.txt,.text,.log,.json"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>

        {/* source_path */}
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1.5">
            来源路径(source_path)
          </label>
          <div className="relative">
            <FileText className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-muted" />
            <input
              type="text"
              value={sourcePath}
              onChange={(e) => setSourcePath(e.target.value)}
              placeholder="docs/example.md"
              disabled={submitting}
              className="w-full rounded-lg bg-surface-input border border-subtle pl-9 pr-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary transition-colors"
            />
          </div>
        </div>

        {/* file_type */}
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1.5">
            文件类型(file_type)
          </label>
          <select
            value={fileType}
            onChange={(e) => setFileType(e.target.value)}
            disabled={submitting}
            className="w-full rounded-lg bg-surface-input border border-subtle px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-primary transition-colors"
          >
            {FILE_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}({t.value})
              </option>
            ))}
          </select>
        </div>

        {/* content */}
        <div>
          <label className="block text-xs font-medium text-text-secondary mb-1.5">
            文档内容(选填,留空则由后端按 source_path 读取)
          </label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={7}
            placeholder="粘贴文档文本,或通过上方文件选择自动填入…"
            disabled={submitting}
            className="w-full rounded-lg bg-surface-input border border-subtle px-3 py-2 text-sm text-text-primary placeholder:text-text-muted font-mono focus:outline-none focus:border-primary transition-colors resize-y"
          />
          {content && (
            <p className="text-[11px] text-text-muted mt-1">
              已载入 {content.length} 字符
            </p>
          )}
        </div>

        {error && (
          <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-status-error/10 text-status-error text-xs">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span className="break-all">{error}</span>
          </div>
        )}
      </div>
    </Modal>
  );
}
