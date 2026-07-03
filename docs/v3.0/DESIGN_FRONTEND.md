# DialogMesh v3.0 前端架构设计

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 框架 | React | 18.x |
| 语言 | TypeScript | 5.x |
| 构建 | Vite | 5.x |
| 样式 | Tailwind CSS | 3.x |
| 路由 | React Router | 6.x |
| 状态 | React Context + useReducer | 原生 |
| HTTP | Fetch API | 原生 |
| WebSocket | 原生 WebSocket API | 原生 |
| 图标 | Lucide React | 最新 |
| 字体 | Inter (英文) + Noto Sans SC (中文) | Google Fonts |

## 设计原则

1. **低饱和暖色调**：避免蓝紫渐变，使用米白/暖灰/浅橙背景
2. **清晰层次**： ample whitespace，卡片阴影微分层
3. **技术术语不翻译**：Cognitive Tree、Fusion Engine、SchemaGuard 等保留英文
4. **Unicode 数学符号**：上下文复杂度评分等用 ℕ、→、≠ 等纯文本符号
5. **响应式**：支持桌面端（主目标）和移动端适配

## 项目结构

```
frontend/
├── public/
│   └── favicon.svg
├── src/
│   ├── main.tsx              # 入口
│   ├── App.tsx               # 根路由
│   ├── index.css             # Tailwind + 全局样式
│   ├── types/
│   │   └── api.ts            # API 类型定义（与后端对齐）
│   ├── api/
│   │   ├── client.ts         # REST API 封装
│   │   └── websocket.ts      # WebSocket 封装
│   ├── hooks/
│   │   ├── useSession.ts     # 会话管理
│   │   ├── useWebSocket.ts   # WebSocket 连接
│   │   └── useAgentStatus.ts # 系统状态轮询
│   ├── components/
│   │   ├── Layout.tsx        # 页面布局（侧边栏 + 主内容区）
│   │   ├── Sidebar.tsx       # 会话列表侧边栏
│   │   ├── ChatPanel.tsx     # 对话面板（消息列表 + 输入框）
│   │   ├── MessageBubble.tsx # 消息气泡（用户/AI/系统）
│   │   ├── ThinkingBlock.tsx # AI 思考过程展示
│   │   ├── ClarificationPanel.tsx # 澄清请求面板
│   │   ├── TaskGraphPanel.tsx # 任务图可视化
│   │   ├── StatusBar.tsx     # 底部状态栏
│   │   └── Dashboard.tsx     # 系统仪表盘
│   ├── pages/
│   │   ├── ChatPage.tsx      # 主对话页面
│   │   └── DashboardPage.tsx # 系统状态页面
│   └── utils/
│       └── format.ts         # 时间/文本格式化
├── index.html
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── vite.config.ts
```

## 页面设计

### 1. ChatPage（主页面）

布局：
```
┌────────────────────────────────────────────────────┐
│  DialogMesh  v3.0                      [仪表盘] [设置] │  ← 顶部导航栏
├──────────┬───────────────────────────────────────────┤
│ 会话列表 │                                           │
│ ┌────┐   │  系统: 检测到模糊意图，请选择：            │  ← 澄清面板
│ │New │   │  [ ] 读取内存值  [ ] 修改内存值  [自定义] │
│ └────┘   │                                           │
│ ──────   ├───────────────────────────────────────────┤
│ 会话1    │  用户: 把 0x1234 的值改掉                 │  ← 消息气泡
│ 会话2    │                                           │
│ 会话3    │  AI (thinking...):                        │  ← 思考中动画
│          │  ├── PCR: scan_memory → confidence 0.82  │
│          │  ├── Intent: modify_memory → score 0.71   │
│          │  └── Fusion: 需要澄清（conflict detected）│
│          │                                           │
│          │  AI: 您希望读取还是修改 0x1234 的值？      │  ← 最终回复
│          │                                           │
│          ├───────────────────────────────────────────┤
│          │  [输入消息...]              [发送] [▲]   │  ← 输入框
└──────────┴───────────────────────────────────────────┘
```

### 2. DashboardPage（仪表盘）

```
┌────────────────────────────────────────────────────┐
│  DialogMesh  Dashboard                    [返回]  │
├────────────────────────────────────────────────────┤
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│  │ 健康状态│ │ 活跃会话│ │ 总请求 │ │ 平均延迟│    │  ← 指标卡片
│  │  ✅    │ │   3    │ │  128   │ │  45ms  │    │
│  └────────┘ └────────┘ └────────┘ └────────┘    │
│                                                    │
│  ┌────────────────────────────────────────────┐   │
│  │  会话状态分布                              │   │  ← 简单图表
│  │  ACTIVE: 3  IDLE: 1  CLARIFYING: 0       │   │
│  └────────────────────────────────────────────┘   │
│                                                    │
│  ┌────────────────────────────────────────────┐   │
│  │  LLM 实例状态                              │   │
│  │  PCR-LLM: 🟢  Intent-LLM: 🟢  Planning: 🟢 │   │
│  │  Meta-Cog: 🟢  Reflective: 🟢  Answer: 🟢  │   │
│  └────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
```

## API 对接

### REST API

```typescript
// POST /v3/session
interface CreateSessionRequest {
  tenant_id?: string;
  user_id?: string;
  process_name?: string;
  pid?: number;
  initial_context?: Record<string, any>;
  preferred_language?: string;
}

interface CreateSessionResponse {
  session_id: string;
  created_at: number;
  ws_url: string;
  status: string;
  capabilities: string[];
  session_ttl_seconds: number;
}

// POST /v3/session/{sid}/message
interface SendMessageRequest {
  content: string;
  modality?: string;
}

interface SendMessageResponse {
  message_id: string;
  session_id: string;
  status: string;
  content?: string;
  response_format: string;
  latency_ms: number;
  clarifications: Ambiguity[];
  suggestions: string[];
}

// GET /v3/session/{sid}/history
interface HistoryResponse {
  session_id: string;
  messages: HistoryRecord[];
  has_more: boolean;
  total_turns: number;
}

interface HistoryRecord {
  sequence: number;
  timestamp: number;
  role: "user" | "agent" | "system";
  content: string;
  latency_ms: number;
}

// GET /v3/session/{sid}/status
interface SessionStatusResponse {
  session_id: string;
  state: string;
  current_turn: number;
  pending_clarification?: string;
  last_activity_at: number;
  expires_at: number;
}
```

### WebSocket 协议

```typescript
// 客户端 → 服务端
interface ClientMessage {
  type: "ping" | "message" | "clarify" | "get_status" | "heartbeat";
  payload: Record<string, any>;
  client_timestamp?: number;
  request_id?: string;
}

// 服务端 → 客户端
interface ServerEvent {
  type: string;  // EventType enum
  session_id: string;
  payload: Record<string, any>;
  timestamp: number;
}

// EventType 枚举
// - HEARTBEAT: 心跳响应
// - MESSAGE: 消息确认/回复
// - CLARIFICATION: 澄清请求/响应
// - SYSTEM_STATUS: 系统状态更新
// - ERROR: 错误
// - TASK_GRAPH_UPDATE: 任务图更新
// - COGNITIVE_TREE_UPDATE: 认知树更新
// - THINKING_START: AI 开始思考
// - THINKING_STEP: AI 思考步骤
// - THINKING_END: AI 思考结束
```

## 状态管理

### 全局 State（React Context）

```typescript
interface AppState {
  // 当前会话
  currentSessionId: string | null;
  sessions: SessionInfo[];
  
  // 消息
  messages: Message[];
  
  // 系统状态
  systemStatus: SystemStatus | null;
  
  // 连接状态
  wsConnected: boolean;
  wsReconnecting: boolean;
  
  // 思考过程
  thinking: ThinkingProcess | null;
  
  // 待澄清
  pendingClarification: ClarificationRequest | null;
  
  // 加载状态
  isLoading: boolean;
}
```

## 关键交互流程

### 1. 创建会话 → 发送消息

```
用户点击 "New Chat"
  → POST /v3/session
  → 获取 session_id + ws_url
  → 连接 WebSocket /v3/ws/{session_id}
  → 用户输入消息
  → WS send {type: "message", payload: {content: "..."}}
  → 服务端返回确认
  → 服务端广播 AI 思考事件 (THINKING_START → THINKING_STEP → THINKING_END)
  → 服务端广播最终回复 (MESSAGE)
  → 前端渲染 MessageBubble
```

### 2. 澄清交互

```
服务端广播 CLARIFICATION 事件
  → 前端渲染 ClarificationPanel
  → 用户选择选项或输入自由文本
  → WS send {type: "clarify", payload: {clarification_id, selected_option, free_text}}
  → 服务端处理并广播结果
```

### 3. 重连逻辑

```
WebSocket 断开
  → 显示 "Reconnecting..." 状态
  → 指数退避重试 (1s → 2s → 4s → 8s, max 30s)
  → 重连成功 → 恢复会话状态
  → 重连失败 → 提示用户手动刷新
```

## 样式规范

### 颜色系统

```css
/* 主色调 */
--primary: #D97706;        /* 琥珀色（暖橙） */
--primary-light: #FCD34D;  /* 浅琥珀 */
--primary-dark: #B45309;   /* 深琥珀 */

/* 背景 */
--bg-main: #FDFCF8;        /* 暖米白 */
--bg-sidebar: #F5F0E8;     /* 暖灰 */
--bg-card: #FFFFFF;        /* 纯白 */
--bg-thinking: #FEF3C7;    /* 浅琥珀 */

/* 文字 */
--text-primary: #1F2937;   /* 深灰 */
--text-secondary: #6B7280;  /* 中灰 */
--text-muted: #9CA3AF;     /* 浅灰 */
--text-ai: #D97706;        /* 琥珀 */

/* 状态 */
--status-success: #10B981; /* 绿 */
--status-warning: #F59E0B; /* 橙 */
--status-error: #EF4444;   /* 红 */
--status-info: #3B82F6;    /* 蓝 */
```

### 字体

```css
font-family: "Inter", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
```

## 开发计划

| 阶段 | 内容 | 预计时间 |
|------|------|----------|
| 1 | 初始化项目 + 配置 Tailwind | 10 min |
| 2 | 实现 Layout + Sidebar + 路由 | 20 min |
| 3 | 实现 API Client + WebSocket Hook | 20 min |
| 4 | 实现 ChatPanel（消息气泡 + 输入框） | 30 min |
| 5 | 实现 ThinkingBlock + ClarificationPanel | 20 min |
| 6 | 实现 DashboardPage | 15 min |
| 7 | 联调测试 + 样式微调 | 15 min |

总计约 2.5 小时。
