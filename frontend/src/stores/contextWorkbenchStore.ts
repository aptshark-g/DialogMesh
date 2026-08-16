/** 上下文工作台本地状态(P1-B)。
 *
 *  钉住/移除仅前端表达(对应后端需求 B3: 记忆片段级钉住/移除接口落地前):
 *   - 键 = 片段内容指纹(后端条目无稳定 ID, 见 B10);
 *   - 存活期 = 本次前端会话(不持久化 — 编译结果每轮变化,
 *     持久化会让"已钉住"标记复活到已不存在的条目上);
 *   - 模块级 store: 切换副槽表面组件卸载后状态仍保留。
 */
import { create } from 'zustand';

export type EntryMark = 'pinned' | 'removed';

interface ContextWorkbenchState {
  /** 指纹 → 标记; 无键 = 正常态 */
  marks: Record<string, EntryMark>;
  togglePin: (key: string) => void;
  toggleRemove: (key: string) => void;
  resetMarks: () => void;
}

export const useContextWorkbench = create<ContextWorkbenchState>((set) => ({
  marks: {},
  togglePin: (key) =>
    set((s) => {
      const marks = { ...s.marks };
      if (marks[key] === 'pinned') delete marks[key];
      else marks[key] = 'pinned'; // 钉住覆盖移除态
      return { marks };
    }),
  toggleRemove: (key) =>
    set((s) => {
      const marks = { ...s.marks };
      if (marks[key] === 'removed') delete marks[key];
      else marks[key] = 'removed';
      return { marks };
    }),
  resetMarks: () => set({ marks: {} }),
}));

/** 条目本地指纹: 后端 /v6/context 条目无 ID(B10), 用内容散列做会话内稳定键 */
export function entryKey(e: { domain?: string; type?: string; content?: string }): string {
  const s = `${e.domain ?? ''}|${e.type ?? ''}|${e.content ?? ''}`;
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h.toString(36);
}
