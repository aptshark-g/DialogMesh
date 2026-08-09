# SVG 流程图编辑器 — 交互设计文档

> 目标：WPS 流程图级交互体验，对标 Figma/WPS 操作习惯

## 一、节点操作

### 1.1 拖拽移动
- 鼠标按下节点 → 拖动 → 松开定位
- 移动时半透明 + 投影增强

### 1.2 缩放 (Vivo 原子组件风格)
- hover 节点 → 右下角出现 Φ8px 蓝色圆点 (`cursor: nwse-resize`)
- 按住圆点拖动 → 节点等比缩放（维持宽高比 3:1）
- 松开 → 文字根据新宽度重新排版（截断 + `...`）

### 1.3 选中态
- 单击节点 → 选中（蓝色边框 2px + 四向连接点显示）
- 单击空白 → 取消选中
- 选中后 Backspace/Delete → 删除节点及其连线

### 1.4 双击编辑
- 双击节点文字 → 出现 `<input>` 或 `contentEditable` 覆盖层
- Enter/失焦 → 确认；Esc → 取消

## 二、连线操作

### 2.1 连接点 (Handle)
- 选中节点时显示四个连接点（上/下/左/右，Φ10px，白底蓝边）
- 非选中节点 hover 时也显示连接点（半透明）
- 从连接点拖出 → 显示虚线跟随鼠标 → 松到目标节点连接点 → 创建连线

### 2.2 自动路由模式 (默认)
- 连线自动计算贝塞尔曲线路径
- 路径经过其他节点时自动绕行（A* 或简单避障）
- 连线颜色根据状态（pending=灰, running=蓝, completed=绿, failed=红）

### 2.3 手动路由模式 (PS 钢笔工具风格)
- 切换到手动画线模式（画布小工具栏切换）
- 从连接点拖出线 → 每次单击添加控制点
- 双击终点/目标连接点 → 完成路径
- 已存在的线：单击连线上任意位置 → 添加控制点
- 控制点可独立拖动

### 2.4 连线操作
- 单击连线 → 选中（高亮 + 显示控制点）
- 选中后 Backspace → 删除连线
- 双击连线 → 添加标签文字

## 三、画布小工具栏 (Canvas Widget)

### 3.1 位置 & 外观
- 固定在画布左上角（跟随视口，不跟随缩放）
- 默认折叠为 Φ36px 圆形按钮（显示 "+" 或工具图标）
- 点击展开 → `w-[200px]` 竖向面板，背景半透明毛玻璃

### 3.2 面板内容

```
┌─────────────────────┐
│ ⊕ 添加节点          │ ← 点击展开节点类型列表
│   · 开始/结束        │
│   · 处理节点         │
│   · 判断节点         │
│   · 子流程           │
├─────────────────────┤
│ 连线模式: [自动 ▾]  │ ← 下拉切换 auto/manual
├─────────────────────┤
│ 点击行为: [选中 ▾]  │ ← 切换 select/delete
├─────────────────────┤
│ 📐 自动布局         │ ← 拓扑排序排列
│ 🔄 重置视图         │ ← fit-to-screen
│ ─                   │ ← 折叠面板
└─────────────────────┘
```

### 3.3 交互
- 面板可拖动（标题栏按住拖动）
- 面板右下角有缩放 handle（调整面板大小）
- 点击画布空白 → 面板可自动折叠（可选设置）

## 四、节点类型系统

```typescript
type NodeType = 'start' | 'end' | 'process' | 'decision' | 'subprocess';

interface FlowNode {
  id: string;
  type: NodeType;
  label: string;
  x: number; y: number;
  width: number; height: number;  // min 120×36, max 400×120
  style?: { fill?: string; stroke?: string };
}

interface FlowEdge {
  id: string;
  source: string; sourceHandle: 'top' | 'bottom' | 'left' | 'right';
  target: string; targetHandle: 'top' | 'bottom' | 'left' | 'right';
  mode: 'auto' | 'manual';
  controlPoints?: { x: number; y: number }[];  // manual mode only
  label?: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
}
```

## 五、技术实现

### 5.1 缩放交互
```
NodeResizeHandle:
  - 绝对定位于节点右下角：x = node.x + node.width, y = node.y + node.height
  - onMouseDown → 记录初始尺寸 + 鼠标位置
  - mousemove → newWidth = initWidth + (mouseX - initMouseX)
  - height = width / 3 (固定比例)
  - 限制: 80 ≤ width ≤ 400
```

### 5.2 自动路由 (Auto)
```
简化为 3 段式路由：
- 从 source handle 出发直线到第一个折点
- 折点经过 source 和 target 的中间区域
- 从折点直线到 target handle
- 检测路径上是否有其他节点 → 偏移避开
```

### 5.3 手动路由 (Manual)
```
- mode='manual' 时，连线上每个 controlPoint 可拖动
- 渲染为 polyline + 贝塞尔平滑
- 双击路径添加控制点
- 右键控制点删除
```

## 六、快捷键

| 键 | 功能 |
|----|------|
| V | 选择模式 |
| D | 删除模式 |
| A | 自动连线模式 |
| M | 手动连线模式 |
| Delete | 删除选中 |
| Ctrl+Z | 撤销 |
| Ctrl+Shift+Z | 重做 |
| Space+拖拽 | 画布平移 |
| Ctrl+滚轮 | 缩放 |

## 七、实施顺序

P0: 基础交互 — 节点拖拽 + 选中 + 四向连接点 + 连线
P1: 缩放 handle + 双击编辑文字
P2: 画布小工具栏 + 自动路由
P3: 手动路由 + 控制点编辑
P4: 撤销/重做 + 自动布局
