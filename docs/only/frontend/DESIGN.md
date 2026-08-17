# DialogMesh 前端设计语言 — 液体玻璃材质体系

> 版本:v2(2026-08-16,P1-E ~ P1-O 沉淀;含 rim 边缘追光体系统一)
> 基调:youmind 式简约骨架 + Apple Liquid Glass 的克制版质感
> 适用:`frontend/` 全部新 UI;老页面逐步迁移

---

## 1. 五条核心原则

1. **基底平直,质感只给浮层** — 页面基底保持纯色/微渐变;玻璃、rim light、追光只属于浮于内容之上的层(下拉、面板、浮卡、结构条)。
2. **立体感来自光影,不来自更粗的线** — 分隔用 hairline + 柔和投影(shadow-bar/shadow-float);卡片之间靠灰度阶梯,不堆描边。
3. **单一光源方向:上方** — 所有内高光统一 `inset 0 1px 0`(顶缘受光),rim 渐变统一 165deg(顶亮底暗),投影统一向下。全站不得出现"从下方打光"的元素。
4. **backdrop-blur 只给会"透出内容"的层** — 元素背后必须有会动的内容(滚动的消息流、被遮罩的页面),模糊才有意义;贴在静态背景上的元素加 blur 是白付性能。
5. **真折射不做** — SVG feDisplacementMap / feSpecularLighting / WebGL shader 复刻的真液体折射,性能与可访问性成本高,业界建议仅用于高曝光小组件;我们用 rim + 内高光 + 追光达到 80% 观感。
6. **追光照亮边缘,不照亮面板** — 面板中央的大光晕是"雾"不是玻璃(P1-M 教训);玻璃追光分两层:表面微光(淡,辅助光泽) + rim 环带追光(mask-composite 差集裁 1.5px 边缘环,鼠标近哪段边缘哪段亮,物理对应"光透过玻璃照亮磨砂倒角")。业界同款:Win10 Fluent 边框照亮 / Cruip spotlight card / antd BorderBeam。

## 2. 材质层级(全部走双主题 CSS 变量)

| 材质类 | 用途 | 配方要点 |
|---|---|---|
| `.glass-panel` | 浮层(omnibox/切换器/下拉菜单/浮坞) | --bg-glass(72%)基底 + backdrop blur(24px) saturate(1.5) + 渐变 rim border + 顶内高光 + 底内阴影 + shadow-float |
| `.glass-panel-strong` | 面板级浮卡(右坞) | 同上但基底 --bg-glass-strong(86%),保密集文字可读 |
| `.card-liquid` | 页面级卡片(全站 9 页 60 张) | --bg-card-liquid(62~78%)基底 + 克制 rim(62% 渐隐);**无 backdrop-filter**(背后是静态底,省开销);双层追光(见原则 6): ::before 表面微光(280px circle, --card-spec-color) + ::after rim 环带追光(1.5px mask 差集环, 240px circle, --card-rim-glow);配 `shadow-card` |
| 结构条(顶栏/输入条) | 浮于滚动内容的横条 | bg-glass + blur + hairline + `.shadow-bar-b/t`(软投影 + inset 顶内高光) |
| `.spec-item` | 按钮/导航项指针聚光 + rim | ::before 110px 径向渐变跟 --mx/--my,`border-radius:inherit` 自裁圆角;::after 130px rim 环带(mask 差集,见 §5.5),小尺寸下边缘几乎全程被点亮;hover 淡入 |
| `.spec-panel` | 浮层表面追光(sheen)+ rim | ::before 320px 大半径低透明度 sheen;::after 320px rim 环带,浮层边缘随鼠标流光 |
| `bg-scrim` | 遮罩 | 独立 token(**类名禁止带 bg-surface 前缀**,见 §5 禁区) |

关键 token(双主题定义于 `index.css`):`--bg-glass / --bg-glass-strong / --bg-card-liquid / --bg-scrim / --bg-wash(-strong)`,`--glass-rim-top/mid/bot / --glass-hi / --glass-losh`,`--shadow-float / --shadow-bar-color`,`--spec-color / --spec-panel-color / --card-spec-color / --card-rim-glow`,`--border-hairline`。

## 3. 双主题规则

- **暗色**:光斑 = 白色低透明(--spec-color 0.10 / panel 0.05 / card 0.04);rim 顶缘近白 0.22;卡片 rim 追光白 0.50(1.5px 细带需高透明度才可见)。
- **亮色**:**白光斑在浅底上无对比,一律换品牌琥珀色**(rgba(217,119,6) 0.14 / 0.08 / card 0.07 / rim 追光 0.45);rim 顶缘近白 0.85(亮色靠边缘光定义形体);投影用暖棕(rgba(60,50,30,*))不用纯黑。
- 新颜色一律进 token,禁止写死 hex 到组件(light.css/dark.css 通配重映射是历史包袱,新类名要绕开其选择器)。

## 4. 交互规范

- **指针追光**:按钮/浮层统一用 `lib/spec.ts` 的 `specMove`(每帧仅写 2 个 CSS 变量,小面积重绘,无 layout);card-liquid 走 `main.tsx` 全局 pointermove 委托(单监听器 closest 命中写变量,覆盖现有/未来全部卡片,零 JSX 侵入);不为高光新建 DOM 层。
- **hover 滑动药丸**:侧栏导航共享 `layoutId="nav-hover-pill"` 的 motion.span 弹簧滑动(stiffness 680 / damping 45,P1-L 提速);激活项用静态 wash,不叠药丸。右坞切换器用独立 `layoutId="dock-switcher-pill"`(700/45,更敏捷)。
- **面板开合**:spring/短时长 ease-out;esc/点外关闭;遮罩用 bg-scrim。

## 5. 禁区与教训(踩过的坑)

1. **`overflow:hidden` 会裁掉 layoutId 动画** — 共享药丸靠 transform 从旧位置飞入,父级 overflow 裁剪让飞行过程不可见,表现为"冒出来"。需要圆角裁剪时,裁在伪元素自身(`border-radius: inherit`),不要裁父级。(P1-J 回归)
2. **light.css/dark.css 的 `[class*="bg-surface"]` 等通配规则特异性极高** — 新工具类命名不得包含 `bg-surface`/`border-gray` 等被通配的词根;优先纯 token 类名(bg-scrim 的诞生即因此,P1-H 亮色全白 bug)。
3. **tailwind.config 的 colors 嵌套不生成工具类** — `colors.border.*` 只生成 `border-border-*`;新层级色必须在 `@layer utilities` 显式补类(P1-F 白线根因)。
4. **拖拽宽度时禁过渡** — transition-all 会让拖拽跟随迟滞,拖拽期间切 `transition-none`。
5. **mask 环带要双写兜底** — rim 追光的 `mask-composite: exclude` 必须配 `-webkit-mask-composite: xor`;两层 mask 都是 `linear-gradient(#fff 0 0)`,内层止于 content-box、外层铺满,差集即环带;伪元素上的 `padding` 值即环带厚度(全站统一 1.5px)。环带色用 `--card-rim-glow`(1.5px 细带必须高透明度才可见:暗白 0.50 / 亮琥珀 0.45,别用低透明度光斑色)。

## 6. 文件地图

- token + 材质类:`src/index.css`(:root/:root.light + @layer components/utilities)
- 旧静态色重映射(逐步退役):`src/light.css` / `src/dark.css`
- 追光 handler:`src/lib/spec.ts`(按钮/浮层,React 挂法);卡片全局委托:`src/main.tsx`(单 pointermove 监听器 → closest('.card-liquid') 写 --mx/--my)
- 主题:`src/stores/themeStore.ts`
- 参考实现:Toolbar(结构条)、OmniboxPalette(浮层全家桶)、Sidebar(spec-item 双层追光 + 拖拽 + edge-fade-r)、SidePanel(glass-panel-strong)、MetaCenterPage(card-liquid 双层追光铺满)

## 7. 后续方向(已拍板备忘)

- 内容呈现关系调整(主槽/副槽/浮层的职责再梳理,先骨架后调)
- B11/B12(图结构选上下文 / 上下文精调)落地后,工作台模式页签接回真实能力
- 浅色 rim 琥珀浓度按真实使用微调(当前 0.45 偏克制)
- 已完成划账:card-liquid 全站 9 页 60 张铺开(P1-L)、双层追光体系(表面微光+rim 环带, P1-M/N)、rim 统一 spec-item/spec-panel(P1-O)、会话/设置页顶距(P1-O)
