import { useCallback, useEffect, useState } from 'react';
import { Globe, Database, ScrollText, Loader2, RefreshCw, Pencil, Save, X } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '../lib/utils';
import { ApiConfigPanel } from '../components/ApiConfigPanel';
import { Toast } from '../components/ui/Toast';
import { getRules, editRule, getHealth, getMetrics, getProviders, getPersistence } from '../api/v6';
import type { V6Rule, V6MetricsResponse, V6ProvidersResponse, V6PersistenceResponse } from '../types/api';

interface RuleEditForm {
  confidence: string;
  conclusion: string;
}

export function SettingsPage() {
  const [rules, setRules] = useState<V6Rule[] | null>(null);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [editingRule, setEditingRule] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<RuleEditForm>({ confidence: '', conclusion: '' });
  const [savingRule, setSavingRule] = useState(false);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [health, setHealth] = useState<{ status: string; version: string } | null>(null);
  const [metrics, setMetrics] = useState<V6MetricsResponse | null>(null);
  const [providers, setProviders] = useState<V6ProvidersResponse | null>(null);
  const [persistence, setPersistence] = useState<V6PersistenceResponse | null>(null);
  const [sysLoading, setSysLoading] = useState(false);

  const loadSystem = useCallback(async () => {
    setSysLoading(true);
    try {
      const [h, m, p, pers] = await Promise.all([
        getHealth().catch(() => null),
        getMetrics().catch(() => null),
        getProviders().catch(() => null),
        getPersistence().catch(() => null),
      ]);
      if (h) setHealth(h);
      if (m) setMetrics(m);
      if (p) setProviders(p);
      if (pers) setPersistence(pers);
    } catch { } finally { setSysLoading(false); }
  }, []);

  useEffect(() => { loadSystem(); }, [loadSystem]);

  const loadRules = useCallback(async () => {
    setRulesLoading(true);
    try {
      const resp = await getRules();
      setRules(resp.rules ?? []);
    } catch (err) {
      setRules(null);
      setToast({
        type: 'error',
        message: `规则加载失败: ${err instanceof Error ? err.message : '未知错误'}`,
      });
    } finally {
      setRulesLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRules();
  }, [loadRules]);

  const handleClearCache = () => {
    const keys = Object.keys(localStorage).filter((k) => k.startsWith('dialogmesh_'));
    keys.forEach((k) => localStorage.removeItem(k));
    console.log('Cleared localStorage keys:', keys);
    alert('本地缓存已清除');
  };

  const startEdit = (rule: V6Rule) => {
    setEditingRule(rule.name);
    setEditForm({
      confidence: String(rule.confidence),
      conclusion: JSON.stringify(rule.conclusion, null, 2),
    });
  };

  const cancelEdit = () => {
    setEditingRule(null);
  };

  const saveRule = async (rule: V6Rule) => {
    let conclusion: Record<string, unknown> | undefined;
    const conclusionText = editForm.conclusion.trim();
    if (conclusionText) {
      try {
        conclusion = JSON.parse(conclusionText) as Record<string, unknown>;
      } catch {
        setToast({ type: 'error', message: 'Conclusion 不是合法 JSON,请检查后重试' });
        return;
      }
    }
    let confidence: number | undefined;
    if (editForm.confidence.trim() !== '') {
      confidence = Number(editForm.confidence);
      if (Number.isNaN(confidence) || confidence < 0 || confidence > 1) {
        setToast({ type: 'error', message: '置信度需为 0-1 之间的数字' });
        return;
      }
    }

    setSavingRule(true);
    try {
      await editRule({ name: rule.name, conclusion, confidence });
      setToast({ type: 'success', message: `规则 ${rule.name} 已保存` });
      setEditingRule(null);
      await loadRules();
    } catch (err) {
      setToast({
        type: 'error',
        message: `保存失败: ${err instanceof Error ? err.message : '未知错误'}`,
      });
    } finally {
      setSavingRule(false);
    }
  };

  return (
    <>
      {toast && (
        <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} />
      )}
      <div className="h-full flex flex-col max-w-5xl mx-auto">
        <div className="mb-4">
          <h1 className="text-2xl font-bold text-text-primary">设置</h1>
          <p className="text-sm text-text-secondary mt-1">
            配置 DialogMesh 前端连接参数
          </p>
        </div>

        <div className="space-y-4">
          <ApiConfigPanel />

          {/* System Info Cards */}
          <motion.div initial={{opacity:0,y:10}} animate={{opacity:1,y:0}} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="bg-surface-card rounded-xl border p-4">
              <div className="flex items-center gap-2 text-text-muted text-xs mb-2">
                <Globe className="w-3.5 h-3.5" /> 引擎状态
              </div>
              <p className="text-lg font-bold text-text-primary">{health?.status ?? '—'}</p>
              <p className="text-xs text-text-muted">v{health?.version ?? '—'}</p>
            </div>
            <div className="bg-surface-card rounded-xl border p-4">
              <div className="flex items-center gap-2 text-text-muted text-xs mb-2">
                <Database className="w-3.5 h-3.5" /> 子系统
              </div>
              <p className="text-lg font-bold text-text-primary">{metrics?.subsystems_loaded ?? '—'}</p>
              <p className="text-xs text-text-muted">已加载 / {metrics?.subsystems_total ?? '—'}</p>
            </div>
            <div className="bg-surface-card rounded-xl border p-4">
              <div className="flex items-center gap-2 text-text-muted text-xs mb-2">
                <ScrollText className="w-3.5 h-3.5" /> 总会话数
              </div>
              <p className="text-lg font-bold text-text-primary">{metrics?.total_turn_count ?? '—'}</p>
              <p className="text-xs text-text-muted">turns</p>
            </div>
            <div className="bg-surface-card rounded-xl border p-4">
              <div className="flex items-center gap-2 text-text-muted text-xs mb-2">
                <RefreshCw className={cn('w-3.5 h-3.5', sysLoading && 'animate-spin')} /> Provider
              </div>
              <p className="text-lg font-bold text-text-primary">{providers?.active_provider ?? '—'}</p>
              <p className="text-xs text-text-muted">{providers?.active_model ?? '—'}</p>
            </div>
          </motion.div>

          {/* Data Persistence */}
          {persistence && (
            <motion.div initial={{opacity:0,y:10}} animate={{opacity:1,y:0}} className="bg-surface-card rounded-xl border p-5">
              <h2 className="text-sm font-semibold text-text-primary mb-3">数据持久化</h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                {Object.entries(persistence).map(([k,v]) => (
                  <div key={k} className="bg-surface-sidebar rounded-lg p-2">
                    <span className="text-text-muted">{k}: </span>
                    <span className="text-text-primary font-medium">{typeof v === 'boolean' ? (v ? '✅' : '—') : String(v ?? '—').substring(0,20)}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Rules Section */}
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

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.4 }}
            className="bg-surface-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-6"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <ScrollText className="w-5 h-5 text-primary" />
                <h2 className="text-base font-semibold text-text-primary">规则管理</h2>
              </div>
              <button
                type="button"
                onClick={loadRules}
                disabled={rulesLoading}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-xs text-text-secondary hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={rulesLoading ? 'w-3.5 h-3.5 animate-spin' : 'w-3.5 h-3.5'} />
                刷新
              </button>
            </div>

            {rulesLoading && !rules && (
              <div className="flex items-center gap-2 py-6 justify-center text-sm text-text-muted">
                <Loader2 className="w-4 h-4 animate-spin" />
                加载规则中...
              </div>
            )}

            {!rulesLoading && rules && rules.length === 0 && (
              <div className="text-sm text-text-secondary py-4">暂无规则</div>
            )}

            {rules && rules.length > 0 && (
              <div className="space-y-3">
                {rules.map((rule) => {
                  const isEditing = editingRule === rule.name;
                  return (
                    <div
                      key={rule.name}
                      className="rounded-lg border border-gray-200 dark:border-gray-700 p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-text-primary truncate">
                              {rule.name}
                            </span>
                            <span className="text-xs px-1.5 py-0.5 rounded bg-surface-sidebar text-text-muted">
                              {rule.source}
                            </span>
                          </div>
                          <div className="text-xs text-text-muted mt-1">
                            置信度 {(rule.confidence * 100).toFixed(0)}% · 命中 {rule.hits} · 未中 {rule.misses}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => (isEditing ? cancelEdit() : startEdit(rule))}
                          className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-xs text-text-secondary hover:text-primary hover:border-primary/40 transition-colors shrink-0"
                        >
                          {isEditing ? <X className="w-3.5 h-3.5" /> : <Pencil className="w-3.5 h-3.5" />}
                          {isEditing ? '取消' : '编辑'}
                        </button>
                      </div>

                      {!isEditing && (
                        <div className="mt-2 space-y-1">
                          <div className="text-xs text-text-muted font-mono bg-surface-sidebar rounded p-2 overflow-x-auto">
                            premise: {JSON.stringify(rule.premise)}
                          </div>
                          <div className="text-xs text-text-secondary font-mono bg-surface-sidebar rounded p-2 overflow-x-auto">
                            conclusion: {JSON.stringify(rule.conclusion)}
                          </div>
                        </div>
                      )}

                      {isEditing && (
                        <div className="mt-3 space-y-2">
                          <div>
                            <label className="text-xs text-text-muted">置信度 (0-1)</label>
                            <input
                              type="number"
                              min={0}
                              max={1}
                              step={0.05}
                              value={editForm.confidence}
                              onChange={(e) =>
                                setEditForm((prev) => ({ ...prev, confidence: e.target.value }))
                              }
                              className="w-full mt-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-surface-sidebar px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-primary"
                            />
                          </div>
                          <div>
                            <label className="text-xs text-text-muted">Conclusion (JSON)</label>
                            <textarea
                              rows={4}
                              value={editForm.conclusion}
                              onChange={(e) =>
                                setEditForm((prev) => ({ ...prev, conclusion: e.target.value }))
                              }
                              className="w-full mt-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-surface-sidebar px-3 py-1.5 text-xs font-mono text-text-primary focus:outline-none focus:border-primary"
                            />
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={() => saveRule(rule)}
                              disabled={savingRule}
                              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
                            >
                              {savingRule ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Save className="w-3.5 h-3.5" />
                              )}
                              {savingRule ? '保存中...' : '保存'}
                            </button>
                            <button
                              type="button"
                              onClick={cancelEdit}
                              disabled={savingRule}
                              className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-xs text-text-secondary hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-50"
                            >
                              取消
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </motion.div>
        </div>
      </div>
    </>
  );
}
