// FILE: frontend/src/pages/ProjectPage.tsx
// 项目页视图 — 工作区信息 + 设计元信息（二阶抽象）+ 项目会话

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowLeft,
  Check,
  Clock,
  FolderOpen,
  MessageSquare,
  PenLine,
  Plus,
  RefreshCw,
  Save,
  Search,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { useV6Sessions } from '../hooks/useV6Sessions';
import { useProjectStore } from '../stores/projectStore';
import { createSession } from '../api/session';
import {
  getProjectDesign,
  saveProjectDesign,
  digestProjectDesign,
  type V6ProjectDesign,
} from '../api/v6';
import { Toast } from '../components/ui/Toast';

const EMPTY_DESIGN: V6ProjectDesign = {
  philosophy: '',
  axioms: [],
  goals: [],
  updated_at: 0,
  source: '',
};

const stripExt = (name: string) => name.replace(/\.json$/, '');

interface ToastState {
  type: 'success' | 'error' | 'info';
  message: string;
}

export function ProjectPage() {
  const { projectId = '' } = useParams();
  const navigate = useNavigate();
  const projects = useProjectStore((s) => s.projects);
  const sessionProject = useProjectStore((s) => s.sessionProject);
  const { sessions, loading, refresh } = useV6Sessions();

  const project = projects.find((p) => p.id === projectId) ?? null;

  // ── 设计元信息（二阶抽象）──
  const [design, setDesign] = useState<V6ProjectDesign>(EMPTY_DESIGN);
  const [designLoading, setDesignLoading] = useState(false);
  const [digesting, setDigesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<ToastState | null>(null);

  const loadDesign = useCallback(async () => {
    if (!projectId) return;
    setDesignLoading(true);
    try {
      setDesign(await getProjectDesign(projectId));
    } catch {
      setDesign(EMPTY_DESIGN);
    } finally {
      setDesignLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadDesign();
  }, [loadDesign]);

  const handleSave = async () => {
    if (!projectId) return;
    setSaving(true);
    try {
      const d = await saveProjectDesign(projectId, {
        philosophy: design.philosophy,
        axioms: design.axioms.filter(Boolean),
        goals: design.goals.filter(Boolean),
        source: 'manual',
      });
      setDesign(d);
      setToast({ type: 'success', message: '设计元信息已保存' });
    } catch (e) {
      setToast({ type: 'error', message: `保存失败: ${e instanceof Error ? e.message : e}` });
    } finally {
      setSaving(false);
    }
  };

  const handleDigest = async () => {
    if (!projectId) return;
    setDigesting(true);
    try {
      const d = await digestProjectDesign(projectId, true);
      setDesign(d);
      setToast({
        type: 'success',
        message: d.source === 'llm_digest' ? '已从项目会话凝练设计元信息（LLM）' : '已生成设计元信息（模板兜底）',
      });
    } catch (e) {
      setToast({ type: 'error', message: `凝练失败: ${e instanceof Error ? e.message : e}` });
    } finally {
      setDigesting(false);
    }
  };

  const handleNewSession = async () => {
    if (!projectId) return;
    try {
      const r = await createSession(projectId);
      // 新建即归属本项目（B16: POST /v3/session 携带 project_id）
      navigate(`/chat/${r.session_id}`);
    } catch (e) {
      setToast({ type: 'error', message: `新建会话失败: ${e instanceof Error ? e.message : e}` });
    }
  };

  const setAxiom = (i: number, v: string) => {
    setDesign((d) => {
      const axioms = [...d.axioms];
      axioms[i] = v;
      return { ...d, axioms };
    });
  };
  const addAxiom = () => setDesign((d) => ({ ...d, axioms: [...d.axioms, ''] }));
  const removeAxiom = (i: number) =>
    setDesign((d) => ({ ...d, axioms: d.axioms.filter((_, x) => x !== i) }));

  const setGoal = (i: number, v: string) => {
    setDesign((d) => {
      const goals = [...d.goals];
      goals[i] = v;
      return { ...d, goals };
    });
  };
  const addGoal = () => setDesign((d) => ({ ...d, goals: [...d.goals, ''] }));
  const removeGoal = (i: number) =>
    setDesign((d) => ({ ...d, goals: d.goals.filter((_, x) => x !== i) }));

  // ── 项目会话 ──
  const [query, setQuery] = useState('');
  const projectSessions = useMemo(
    () => sessions.filter((s) => sessionProject[s.name] === projectId),
    [sessions, sessionProject, projectId]
  );
  const filteredSessions = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? projectSessions.filter((s) => s.name.toLowerCase().includes(q)) : projectSessions;
  }, [projectSessions, query]);

  if (!project) {
    return (
      <div className="min-h-full flex flex-col items-center justify-center text-center px-6">
        <FolderOpen className="h-10 w-10 text-text-muted mb-3" />
        <p className="text-sm text-text-secondary">项目不存在或已被删除</p>
        <button
          type="button"
          onClick={() => navigate('/sessions')}
          className="mt-3 text-xs text-primary hover:underline"
        >
          返回会话页
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-full flex flex-col max-w-5xl mx-auto px-6 lg:px-10 pt-6 pb-10 overflow-y-auto">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-primary transition-colors w-fit mb-4"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        返回
      </button>

      {/* 项目概览 */}
      <div className="card-liquid shadow-card rounded-xl p-5 mb-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-4 min-w-0">
            <div
              className="h-11 w-11 rounded-xl flex items-center justify-center shrink-0 text-white text-lg font-bold"
              style={{ background: project.color }}
            >
              {project.name.slice(0, 1).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-bold text-text-primary flex items-center gap-2">
                {project.name}
                {project.path && (
                  <span className="text-[11px] font-normal text-text-muted bg-wash rounded-full px-2 py-0.5 flex items-center gap-1">
                    <FolderOpen className="w-3 h-3" />
                    <span className="font-mono">{project.path}</span>
                  </span>
                )}
              </h1>
              <div className="flex items-center gap-3 mt-1 text-xs text-text-muted">
                <span className="flex items-center gap-1">
                  <MessageSquare className="w-3 h-3" />
                  {projectSessions.length} 个会话
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {/* createdAt 统一毫秒（兼容旧秒值: >1e12 视为 ms） */}
                  创建于 {new Date(
                    project.createdAt > 1e12 ? project.createdAt : project.createdAt * 1000
                  ).toLocaleString('zh-CN', { hour12: false })}
                </span>
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={handleNewSession}
            className="flex items-center gap-1.5 rounded-lg bg-primary text-white px-3 py-2 text-xs font-medium hover:bg-primary-dark transition-colors shrink-0"
          >
            <Plus className="w-3.5 h-3.5" />
            新建会话
          </button>
        </div>
      </div>

      {/* 设计元信息（二阶抽象） */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="card-liquid shadow-card rounded-xl p-5 mb-4"
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-primary" />
              设计元信息（二阶抽象）
            </h2>
            <p className="text-xs text-text-muted mt-0.5">
              项目的设计理念 / 公理 / 目标 —— 从会话实践中提炼约束, 约束长出来, 不是写出来
            </p>
          </div>
          {design.updated_at > 0 && (
            <span className="text-[11px] text-text-muted">
              {design.source === 'llm_digest' ? 'LLM 凝练' : design.source === 'template' ? '模板生成' : '手动编辑'}
              {' · '}
              {new Date(design.updated_at * 1000).toLocaleString('zh-CN', { hour12: false })}
            </span>
          )}
        </div>

        {designLoading ? (
          <div className="py-8 text-center text-xs text-text-muted">加载设计元信息…</div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-text-secondary flex items-center gap-1.5 mb-1.5">
                <PenLine className="w-3.5 h-3.5" />
                设计理念
              </label>
              <textarea
                value={design.philosophy}
                onChange={(e) => setDesign((d) => ({ ...d, philosophy: e.target.value }))}
                rows={2}
                placeholder="一句话主张: 这个项目「为什么这样做」…"
                className="w-full bg-wash rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40 resize-none"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-medium text-text-secondary flex items-center gap-1.5">
                  <Check className="w-3.5 h-3.5" />
                  设计公理（不可协商的约束）
                </label>
                <button
                  type="button"
                  onClick={addAxiom}
                  className="flex items-center gap-1 text-[11px] text-primary hover:text-primary-dark"
                >
                  <Plus className="w-3 h-3" />
                  添加公理
                </button>
              </div>
              <div className="space-y-1.5">
                {design.axioms.length === 0 && (
                  <p className="text-xs text-text-muted py-1">暂无公理, 可手动添加或点击下方「从项目会话凝练」</p>
                )}
                {design.axioms.map((a, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-xs text-text-muted w-5 text-right font-mono">{i + 1}.</span>
                    <input
                      value={a}
                      onChange={(e) => setAxiom(i, e.target.value)}
                      className="flex-1 bg-wash rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
                    />
                    <button
                      type="button"
                      onClick={() => removeAxiom(i)}
                      aria-label="删除公理"
                      className="p-1 rounded text-text-muted hover:text-status-error transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-medium text-text-secondary flex items-center gap-1.5">
                  <Check className="w-3.5 h-3.5" />
                  设计目标
                </label>
                <button
                  type="button"
                  onClick={addGoal}
                  className="flex items-center gap-1 text-[11px] text-primary hover:text-primary-dark"
                >
                  <Plus className="w-3 h-3" />
                  添加目标
                </button>
              </div>
              <div className="space-y-1.5">
                {design.goals.length === 0 && (
                  <p className="text-xs text-text-muted py-1">暂无目标</p>
                )}
                {design.goals.map((g, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-xs text-text-muted w-5 text-right font-mono">{i + 1}.</span>
                    <input
                      value={g}
                      onChange={(e) => setGoal(i, e.target.value)}
                      className="flex-1 bg-wash rounded-lg px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-primary/40"
                    />
                    <button
                      type="button"
                      onClick={() => removeGoal(i)}
                      aria-label="删除目标"
                      className="p-1 rounded text-text-muted hover:text-status-error transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={handleDigest}
                disabled={digesting}
                className="flex items-center gap-1.5 rounded-lg bg-surface-sidebar border border-subtle px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-primary hover:border-primary/30 transition-colors disabled:opacity-50"
              >
                <Sparkles className={cn('w-3.5 h-3.5', digesting && 'animate-pulse')} />
                {digesting ? '凝练中…' : '从项目会话凝练'}
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1.5 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:bg-primary-dark transition-colors disabled:opacity-50"
              >
                <Save className="w-3.5 h-3.5" />
                {saving ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        )}
      </motion.div>

      {/* 项目会话 */}
      <div className="card-liquid shadow-card rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-subtle space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-primary">
              项目会话
              <span className="ml-2 text-xs font-normal text-text-muted">
                共 {filteredSessions.length} 个
              </span>
            </h2>
            <button
              type="button"
              onClick={refresh}
              disabled={loading}
              className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-primary transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
              刷新
            </button>
          </div>
          <div className="relative">
            <Search className="h-3.5 w-3.5 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索项目内会话…"
              aria-label="搜索项目会话"
              className="w-full bg-wash rounded-lg pl-8 pr-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40"
            />
          </div>
        </div>

        {projectSessions.length === 0 ? (
          <div className="px-5 py-14 text-center">
            <MessageSquare className="h-9 w-9 text-text-muted mx-auto mb-3" />
            <p className="text-sm text-text-secondary">该项目下暂无会话</p>
            <p className="text-xs text-text-muted mt-1">
              新建会话后在会话页点「归入项目」, 或把过去的数据归入本项目
            </p>
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="px-5 py-14 text-center">
            <Search className="h-9 w-9 text-text-muted mx-auto mb-3" />
            <p className="text-sm text-text-secondary">未找到匹配「{query.trim()}」的会话</p>
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {filteredSessions.map((s) => {
              const sid = stripExt(s.name);
              return (
                <div
                  key={s.name}
                  className="flex items-center gap-4 px-5 py-4 hover:bg-surface-card-hover transition-colors group"
                >
                  <div className="h-9 w-9 rounded-lg bg-surface-sidebar flex items-center justify-center shrink-0">
                    <MessageSquare className="h-4 w-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-text-primary truncate">
                      {s.name}
                    </div>
                    <div className="text-xs text-text-muted mt-0.5">
                      {(s.size ?? 0)} 轮
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigate(`/chat/${sid}`)}
                    className="rounded-lg bg-primary/10 text-primary px-3 py-1.5 text-xs font-medium hover:bg-primary/20 transition-colors shrink-0"
                  >
                    进入
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {toast && (
        <Toast
          type={toast.type}
          message={toast.message}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}
