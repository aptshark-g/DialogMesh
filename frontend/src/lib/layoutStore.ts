/** 布局 store(P1-A 双槽位骨架)。
 *
 *  当前职责: 副槽配对记忆(路由前缀 → 表面), localStorage 持久化。
 *  auto(联动)模式下优先使用记忆, 其次用注册表默认配对。
 *
 *  未来扩展:
 *   - 配对偏好跨设备同步 → 需用户偏好端点(UI_REFACTOR_PLAN B8);
 *   - 槽位所有权(用户 / 自动化运行时)与自动化视口配对(B9)。
 */
import { create } from 'zustand';
import type { SurfaceKey } from './surfaceRegistry';

const KEY = 'dm_layout_pairing';

function loadPairing(): Record<string, SurfaceKey> {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '{}');
  } catch {
    return {};
  }
}

interface LayoutState {
  /** 路由前缀 → 用户手动选择过的副槽表面 */
  pairing: Record<string, SurfaceKey>;
  rememberPairing: (route: string, surface: SurfaceKey) => void;
}

export const useLayoutStore = create<LayoutState>((set) => ({
  pairing: loadPairing(),
  rememberPairing: (route, surface) =>
    set((s) => {
      const pairing = { ...s.pairing, [route]: surface };
      try {
        localStorage.setItem(KEY, JSON.stringify(pairing));
      } catch {}
      return { pairing };
    }),
}));
