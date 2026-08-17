import type { PointerEvent as ReactPointerEvent } from 'react';

/** P1-J: 玻璃面板指针追光 — 把指针位置写入元素本地 CSS 变量(--mx/--my)。
 *  配合 .spec-panel / .spec-item 的 ::before 径向渐变使用;
 *  每帧仅写 2 个 CSS 变量, 只触发小面积重绘, 无 layout。 */
export function specMove(e: ReactPointerEvent<HTMLElement>) {
  const el = e.currentTarget;
  const r = el.getBoundingClientRect();
  el.style.setProperty('--mx', `${e.clientX - r.left}px`);
  el.style.setProperty('--my', `${e.clientY - r.top}px`);
}
