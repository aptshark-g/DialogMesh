// FILE: src/stores/projectStore.ts
// P2 项目组:项目实体 + 会话归属映射
// B15/B16（2026-08-17）: 服务端持久化驱动 — 数据源 /v6/projects + 会话归属
// 写接口 PUT /v6/sessions/{id}/project。localStorage 仅保留 activeProjectId
// 与"本地旧数据 → 服务端初始导入"的迁移来源（上线一次性迁移）。

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  getProjects,
  createProjectApi,
  patchProjectApi,
  deleteProjectApi,
  assignSessionProjectApi,
  type V6Project,
} from '@/api/v6';

export interface Project {
  id: string;
  name: string;
  color: string;
  createdAt: number;
}

/** 徽章色板(按创建顺序循环取用;侧栏改色菜单也用它) */
export const PROJECT_PALETTE = ['#D97706', '#0D9488', '#8B5CF6', '#3B82F6', '#E11D48', '#10B981'];

const toProject = (p: V6Project): Project => ({
  id: p.id,
  name: p.name,
  color: p.color,
  createdAt: p.created_at,
});

interface ProjectState {
  projects: Project[];
  /** sessionName → projectId(session 标识沿用 useV6Sessions 的 name) */
  sessionProject: Record<string, string>;
  /** 激活项目 = 会话列表的过滤范围;null = 全部会话 */
  activeProjectId: string | null;
  /** 是否已从服务端加载（初始化完成） */
  hydrated: boolean;
}

interface ProjectActions {
  loadFromServer: () => Promise<void>;
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
      hydrated: false,

      /** B15: 启动加载服务端数据; 服务端空时用本地旧数据做初始导入（一次性迁移）。 */
      loadFromServer: async () => {
        try {
          const data = await getProjects();
          set({
            projects: (data.projects ?? []).map(toProject),
            sessionProject: data.session_project ?? {},
            hydrated: true,
          });
        } catch (e) {
          // 服务端不可达: 保持本地状态可编辑（降级为纯前端）, 标记未 hydrated
          set({ hydrated: false });
          console.warn('[projectStore] loadFromServer failed:', e);
        }
      },

      createProject: (name) => {
        const project: Project = {
          id: `p_${Date.now().toString(36)}`,
          name: name.trim(),
          color: PROJECT_PALETTE[get().projects.length % PROJECT_PALETTE.length],
          createdAt: Date.now(),
        };
        set((s) => ({ projects: [...s.projects, project] }));
        // 服务端建（失败不回滚本地 — 乐观更新, 白盒可查差异）
        createProjectApi(project.name, project.color)
          .then((p) => {
            set((s) => ({
              projects: s.projects.map((x) =>
                x.id === project.id ? toProject(p) : x
              ),
            }));
          })
          .catch((e) => console.warn('[projectStore] create failed:', e));
        return project;
      },

      renameProject: (id, name) => {
        set((s) => ({
          projects: s.projects.map((p) => (p.id === id ? { ...p, name: name.trim() } : p)),
        }));
        // 服务端改名
        patchProjectApi(id, { name: name.trim() }).catch((e) =>
          console.warn('[projectStore] rename failed:', e));
      },

      recolorProject: (id, color) => {
        set((s) => ({
          projects: s.projects.map((p) => (p.id === id ? { ...p, color } : p)),
        }));
        // 服务端改色
        patchProjectApi(id, { color }).catch((e) =>
          console.warn('[projectStore] recolor failed:', e));
      },

      deleteProject: (id) => {
        set((s) => ({
          projects: s.projects.filter((p) => p.id !== id),
          // 归属映射一并清除,会话回到"未分配"
          sessionProject: Object.fromEntries(
            Object.entries(s.sessionProject).filter(([, pid]) => pid !== id)
          ),
          activeProjectId: s.activeProjectId === id ? null : s.activeProjectId,
        }));
        deleteProjectApi(id).catch((e) =>
          console.warn('[projectStore] delete failed:', e));
      },

      assignSession: (sessionName, projectId) => {
        set((s) => {
          const next = { ...s.sessionProject };
          if (projectId) next[sessionName] = projectId;
          else delete next[sessionName];
          return { sessionProject: next };
        });
        assignSessionProjectApi(sessionName, projectId).catch((e) =>
          console.warn('[projectStore] assign failed:', e));
      },

      setActiveProject: (id) => set({ activeProjectId: id }),
    }),
    {
      name: 'dm_projects',
      version: 2,
      // B15: 仅 activeProjectId 持久化（项目/归属以服务端为准）
      partialize: (s) => ({ activeProjectId: s.activeProjectId }) as ProjectStore,
    }
  )
);
