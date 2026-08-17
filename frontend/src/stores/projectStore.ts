// FILE: src/stores/projectStore.ts
// P2 项目组:项目实体 + 会话归属映射,localStorage 持久化
// 后端落地后迁移为服务端持久化(见 UI_REFACTOR_PLAN B15/B16/B17)

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Project {
  id: string;
  name: string;
  color: string;
  createdAt: number;
}

/** 徽章色板(按创建顺序循环取用;侧栏改色菜单也用它) */
export const PROJECT_PALETTE = ['#D97706', '#0D9488', '#8B5CF6', '#3B82F6', '#E11D48', '#10B981'];

interface ProjectState {
  projects: Project[];
  /** sessionName → projectId(session 标识沿用 useV6Sessions 的 name) */
  sessionProject: Record<string, string>;
  /** 激活项目 = 会话列表的过滤范围;null = 全部会话 */
  activeProjectId: string | null;
}

interface ProjectActions {
  createProject: (name: string) => Project;
  renameProject: (id: string, name: string) => void;
  recolorProject: (id: string, color: string) => void;
  deleteProject: (id: string) => void;
  assignSession: (sessionName: string, projectId: string | null) => void;
  setActiveProject: (id: string | null) => void;
}

export type ProjectStore = ProjectState & ProjectActions;

export const useProjectStore = create<ProjectStore>()(
  persist(
    (set, get) => ({
      projects: [],
      sessionProject: {},
      activeProjectId: null,

      createProject: (name) => {
        const project: Project = {
          id: `p_${Date.now().toString(36)}`,
          name: name.trim(),
          color: PROJECT_PALETTE[get().projects.length % PROJECT_PALETTE.length],
          createdAt: Date.now(),
        };
        set((s) => ({ projects: [...s.projects, project] }));
        return project;
      },

      renameProject: (id, name) =>
        set((s) => ({
          projects: s.projects.map((p) => (p.id === id ? { ...p, name: name.trim() } : p)),
        })),

      recolorProject: (id, color) =>
        set((s) => ({
          projects: s.projects.map((p) => (p.id === id ? { ...p, color } : p)),
        })),

      deleteProject: (id) =>
        set((s) => ({
          projects: s.projects.filter((p) => p.id !== id),
          // 归属映射一并清除,会话回到"未分配"
          sessionProject: Object.fromEntries(
            Object.entries(s.sessionProject).filter(([, pid]) => pid !== id)
          ),
          activeProjectId: s.activeProjectId === id ? null : s.activeProjectId,
        })),

      assignSession: (sessionName, projectId) =>
        set((s) => {
          const next = { ...s.sessionProject };
          if (projectId) next[sessionName] = projectId;
          else delete next[sessionName];
          return { sessionProject: next };
        }),

      setActiveProject: (id) => set({ activeProjectId: id }),
    }),
    { name: 'dm_projects', version: 1 }
  )
);
