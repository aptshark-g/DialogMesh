// FILE: src/components/profile/ProfileEditPanel.tsx
// 画像纠正 Tab —— OCEAN 维度滑杆编辑 + MBTI 修改 + 画像→参数自动映射

const OCEAN_LABELS: Record<string, string> = {
  openness: '开放性',
  conscientiousness: '尽责性',
  extraversion: '外向性',
  agreeableness: '宜人性',
  neuroticism: '神经质',
};

const oceanLabel = (key: string) => OCEAN_LABELS[key.toLowerCase()] ?? key;

import { useEffect, useMemo, useState } from 'react';
import type { FC } from 'react';
import { Loader2, Save, Wand2 } from 'lucide-react';
import { editProfile, applyOceanParams } from '@/api/v6';
import type { V6OceanParamsResponse, V6ProfileResponse } from '@/types/api';
import { Toast } from '@/components/ui/Toast';
import { cn } from '@/lib/utils';

type ToastState = {
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
} | null;

interface ProfileEditPanelProps {
  profile: V6ProfileResponse | null;
  onSaved: () => void;
}

const EPS = 1e-6;

export const ProfileEditPanel: FC<ProfileEditPanelProps> = ({ profile, onSaved }) => {
  const [dims, setDims] = useState<Record<string, number>>({});
  const [mbti, setMbti] = useState('');
  const [saving, setSaving] = useState(false);
  const [applying, setApplying] = useState(false);
  const [oceanParams, setOceanParams] = useState<V6OceanParamsResponse | null>(null);
  const [toast, setToast] = useState<ToastState>(null);

  // 画像刷新后同步本地编辑态
  useEffect(() => {
    setDims(profile?.oceAN_dims ? { ...profile.oceAN_dims } : {});
    setMbti(profile?.mbti ?? '');
  }, [profile]);

  const dimEntries = useMemo(() => Object.entries(dims), [dims]);

  const changedDims = useMemo(() => {
    if (!profile) return [] as string[];
    return dimEntries
      .filter(([k, v]) => Math.abs((profile.oceAN_dims[k] ?? 0) - v) > EPS)
      .map(([k]) => k);
  }, [dimEntries, profile]);

  const mbtiDirty =
    Boolean(profile?.mbti) && mbti.trim().toUpperCase() !== (profile?.mbti ?? '');
  const dirty = changedDims.length > 0 || mbtiDirty;

  const handleDimChange = (key: string, pct: number) => {
    if (Number.isNaN(pct)) return;
    const clamped = Math.min(100, Math.max(0, pct));
    setDims((prev) => ({ ...prev, [key]: clamped / 100 }));
  };

  const handleSave = async () => {
    if (!profile || !dirty || saving) return;
    setSaving(true);
    try {
      const tasks = changedDims.map((k) => editProfile({ dim: k, value: dims[k] }));
      if (mbtiDirty) tasks.push(editProfile({ mbti: mbti.trim().toUpperCase() }));
      const results = await Promise.all(tasks);
      const feedback = results.flatMap((r) => r.feedback);
      const updated = results.flatMap((r) => r.updated);
      setToast({
        type: 'success',
        message:
          feedback.length > 0
            ? feedback.join('；')
            : `画像已更新（${updated.length} 个字段）`,
      });
      onSaved();
    } catch (err) {
      setToast({
        type: 'error',
        message: err instanceof Error ? err.message : '保存画像失败',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleApplyParams = async () => {
    if (applying) return;
    setApplying(true);
    try {
      const res = await applyOceanParams();
      setOceanParams(res);
      setToast({ type: 'success', message: '已应用到管道参数，可在管道页查看' });
    } catch (err) {
      setToast({
        type: 'error',
        message: err instanceof Error ? err.message : '参数映射失败',
      });
    } finally {
      setApplying(false);
    }
  };

  if (!profile) {
    return (
      <div className="bg-surface-card rounded-xl border border-border-subtle p-6">
        <h3 className="text-sm font-semibold text-text-primary mb-4">画像纠正</h3>
        <p className="text-sm text-text-muted">画像数据加载后可在此时编辑 OCEAN 维度。</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* OCEAN 维度编辑 */}
      <div className="bg-surface-card rounded-xl border border-border-subtle p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="text-sm font-semibold text-text-primary">OCEAN 维度编辑</h3>
            <p className="text-xs text-text-muted mt-0.5">
              拖动滑杆或输入数值（0–100）调整维度得分，保存后立即写回画像
            </p>
          </div>
          <div className="flex items-center gap-2">
            {dirty && (
              <span className="text-xs px-2 py-1 rounded-full bg-status-warning/10 text-status-warning">
                有未保存更改
              </span>
            )}
            <button
              type="button"
              onClick={handleSave}
              disabled={!dirty || saving}
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium',
                'bg-primary text-white hover:opacity-90 transition-opacity',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              {saving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              保存修改
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
          {dimEntries.map(([key, value]) => {
            const pct = Math.round(value * 100);
            const changed = changedDims.includes(key);
            return (
              <div key={key} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-text-primary">{oceanLabel(key)}</span>
                    {changed && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-status-warning/10 text-status-warning">
                        已修改
                      </span>
                    )}
                  </div>
                  <span className="text-sm font-semibold text-text-primary tabular-nums">
                    {pct}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={0}
                    max={100}
                    step={1}
                    value={pct}
                    onChange={(e) => handleDimChange(key, Number(e.target.value))}
                    className="flex-1 h-2 accent-[#D97706] cursor-pointer"
                    aria-label={`${key} 滑杆`}
                  />
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={1}
                    value={pct}
                    onChange={(e) => handleDimChange(key, Number(e.target.value))}
                    className={cn(
                      'w-16 px-2 py-1 rounded-md text-sm text-text-primary text-right tabular-nums',
                      'bg-surface-sidebar border border-border-subtle',
                      'focus:outline-none focus:border-primary'
                    )}
                    aria-label={`${key} 数值输入`}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* MBTI 编辑（若画像含 MBTI） */}
        {profile.mbti && (
          <div className="mt-6 pt-4 border-t border-border-subtle flex flex-col sm:flex-row sm:items-center gap-3">
            <span className="text-sm font-medium text-text-primary shrink-0">MBTI</span>
            <input
              type="text"
              value={mbti}
              maxLength={4}
              onChange={(e) => setMbti(e.target.value.toUpperCase())}
              placeholder="如 INTP"
              className={cn(
                'w-28 px-3 py-1.5 rounded-md text-sm text-text-primary tracking-widest uppercase',
                'bg-surface-sidebar border border-border-subtle',
                'focus:outline-none focus:border-primary'
              )}
              aria-label="MBTI 输入"
            />
            <span className="text-xs text-text-muted">
              当前画像值：{profile.mbti}，修改后随「保存修改」一并提交
            </span>
          </div>
        )}
      </div>

      {/* 画像→参数自动映射 */}
      <div className="bg-surface-card rounded-xl border border-border-subtle p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
          <div>
            <h3 className="text-sm font-semibold text-text-primary">画像 → 参数自动映射</h3>
            <p className="text-xs text-text-muted mt-0.5">
              将当前 OCEAN 画像自动映射为管道参数（applyOceanParams）
            </p>
          </div>
          <button
            type="button"
            onClick={handleApplyParams}
            disabled={applying}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium',
              'bg-surface-card border border-border-subtle text-text-secondary',
              'hover:bg-surface-card-hover hover:text-primary transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            {applying ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Wand2 className="w-4 h-4" />
            )}
            自动映射参数
          </button>
        </div>

        {oceanParams ? (
          <div className="space-y-4">
            <div className="overflow-x-auto rounded-lg border border-border-subtle">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-surface-sidebar text-left">
                    <th className="px-3 py-2 text-xs font-medium text-text-muted">管道参数</th>
                    <th className="px-3 py-2 text-xs font-medium text-text-muted">映射值</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(oceanParams.applied).map(([k, v]) => (
                    <tr key={k} className="border-t border-border-subtle">
                      <td className="px-3 py-2 text-text-primary font-medium">{k}</td>
                      <td className="px-3 py-2 text-text-secondary">{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {Object.keys(oceanParams.ocean).length > 0 && (
              <div>
                <p className="text-xs text-text-muted mb-2">映射时 OCEAN 快照</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(oceanParams.ocean).map(([k, v]) => (
                    <span
                      key={k}
                      className="text-xs px-2 py-1 rounded-full bg-surface-sidebar text-text-secondary"
                    >
                      {k}: {Math.round(v * 100)}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <p className="text-xs text-status-success">
              已应用到管道参数，可在管道页查看
            </p>
          </div>
        ) : (
          <p className="text-sm text-text-muted">
            点击「自动映射参数」后，此处展示映射出的管道参数键值对。
          </p>
        )}
      </div>

      {toast && (
        <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} />
      )}
    </div>
  );
};

export default ProfileEditPanel;
