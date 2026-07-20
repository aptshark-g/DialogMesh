# DialogMesh v6 — 前端业务流全文档

> 2026-07-20 · 覆盖 14 页面 × 70+ API 调用 × 12 hooks

---

## 一、全局数据流

```
用户操作 → React State → API 调用 → 后端 → 返回数据 → 渲染

启动流程:
  1. start.bat 启动 Gateway(:8080) + API(:8000)
  2. Vite 编译前端 (:4173)
  3. 前端 useV6Gateway 轮询健康检查 (15s)
  4. 健康通过 → 加载 Provider 列表 + 配置 + 用量
  5. 各页面独立调用自己的数据源
```

---

## 二、14 页面业务详解

### 1. Dashboard (`/`) — 系统概览
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | GET /v4/health | 显示 API 状态 |
| 页面加载 | 自动 | GET /v3/health | 显示运行时间 |
| 状态轮询 | 15s | GET /v4/health | 更新状态灯 |

**状态**: ✅ 纯读，无写操作

---

### 2. Chat (`/chat`) — AI 对话
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 打开页面 | 自动 | POST /v3/session | 创建会话，返回 session_id |
| 打开页面 | 自动 | ws_url → 跳过(空) | 不连 WebSocket |
| 输入文字发送 | 点击/回车 | POST /v3/session/{id}/message | AI 回复 |
| 查看历史 | 点击历史按钮 | GET /v3/session/{id}/history | 显示历史列表 |
| 提交澄清 | 回答澄清问题 | POST /v3/session/{id}/clarify | 上下文更新 |

**状态**: ⚠️ concepts 变量已修复，待重启验证

---

### 3. ConversationGraph (`/graph`) — 对话图谱
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | GET /v6/graph | 对话节点+边 |
| 页面加载 | 自动 | GET /v6/discourse-tree | 对话树结构 |
| 点击节点 | 用户点击 | GET /v6/objects | 语义对象详情 |
| 编辑节点 | 用户拖动 | PUT /v6/edit/graph | 保存修改 |
| 编辑关系 | 用户连线 | PUT /v6/edit/relations | 保存关系 |

**状态**: ⚠️ 纯前端 render，写操作需引擎支持

---

### 4. CognitiveProfile (`/profile`) — 认知画像
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | GET /v6/profile | OCEAN 10 维数据 |
| 页面加载 | 自动 | GET /v6/trace | 执行追踪 |
| 页面加载 | 自动 | GET /v6/abc | ABC 规则 |
| 页面加载 | 自动 | GET /v6/mind | Mind 关系 |
| 页面加载 | 自动 | GET /v6/inertia | 惯性权重 |
| 页面加载 | 自动 | GET /v6/belief | 信念数据 |
| 编辑画像 | 输入修改 | PUT /v6/profile | 保存修改 |
| 修正画像 | 点击修正 | POST /v6/profile/corrections/review | 送审元认知 |
| 应用 OCEAN | 点击应用 | POST /v6/ocean/params | 参数反哺 |

**状态**: ✅ 读正常，⚠️ 写依赖引擎

---

### 5. TaskPlanning (`/tasks`) — 任务规划
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | (无 API) | 纯前端占位 |

**状态**: ⚠️ 占位页，无业务逻辑

---

### 6. Gateway (`/gateway`) — 网关管理 ⭐核心
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | GET /v6/gateway/providers | Provider 列表 |
| 页面加载 | 自动 | GET /v6/gateway/config | 网关配置 |
| 页面加载 | 自动 | GET /v6/gateway/usage | 用量统计 |
| 页面加载 | 自动 | GET /v6/gateway/stats | 性能统计 |
| 页面加载 | 自动 | GET /v6/gateway/health | 网关健康 |
| 页面加载 | 自动 | GET /v6/router/modes | 路由模式 |
| 页面加载 | 自动 | GET /v6/providers | 旧Provider |
| 页面加载 | 自动 | GET /v6/providers/tokens | Token统计 |
| 页面加载 | 自动 | GET /v6/metrics | 指标数据 |
| 配置 API Key | 输入+保存 | PUT /v6/gateway/providers/{name} | **持久化到 Gateway** |
| 切换 Provider | 点击激活 | PUT /v6/gateway/active | 切换当前 Provider |
| 测试连接 | 点击测试 | POST /v6/gateway/providers/{name}/test | 连通性测试 |
| 拉取模型列表 | 展开 Provider | POST /v6/gateway/providers/{name}/models | 模型列表 |
| 新增 Provider | 填写表单 | POST /v6/gateway/providers | 添加 Provider |
| 删除 Provider | 点击删除 | DELETE /v6/gateway/providers/{name} | 移除 |
| 修改上下文 | 输入+保存 | PUT /v6/context/config | 上下文配置 |

**状态**: ✅ Key 持久化通过，⚠️ 需 API 在线

---

### 7. Pipeline (`/pipeline`) — 管线可视化
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | GET /v6/pipeline | 管线状态 |
| 页面加载 | 自动 | GET /v6/extraction | 提取状态 |
| 页面加载 | 自动 | GET /v6/perspectives | 视角列表 |

**状态**: ⚠️ 纯前端渲染

---

### 8. DeepChain (`/deepchain`) — 深层链
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | GET /v6/relations | 关系图 |
| 页面加载 | 自动 | GET /v6/causal | 因果晋升 |
| 页面加载 | 自动 | GET /v6/behavior | 行为发现 |
| 页面加载 | 自动 | GET /v6/engineering | 工程链 |
| 页面加载 | 自动 | GET /v6/belief | 信念凝聚 |
| 页面加载 | 自动 | GET /v6/subgraph/cache | 子图缓存 |

**状态**: ✅ 读正常

---

### 9. MetaCenter (`/meta`) — 元认知中心
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | GET /v6/meta/stats | 元认知统计 |
| 页面加载 | 自动 | GET /v6/meta/queue | 审核队列 |
| 触发扫描 | 点击扫描 | POST /v6/meta/scan | 启动元认知扫描 |
| 触发复盘 | 点击复盘 | POST /v6/meta/retrospect | 启动复盘 |
| 查看版本 | 选择分类 | GET /v6/versions/{category} | 版本历史 |
| 回滚版本 | 点击回滚 | POST /v6/versions/{category}/rollback | 回滚到指定版本 |

**状态**: ✅ 读正常，⚠️ 写依赖引擎

---

### 10. Behavior (`/behavior`) — 行为发现
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | GET /v6/behavior/patterns | 行为模式列表 |
| 页面加载 | 自动 | GET /v6/behavior/predictions | 行为预测 |
| 页面加载 | 自动 | GET /v6/inertia | 惯性权重图 |
| 审核模式 | 点击审核 | POST /v6/behavior/feedback | 反馈模式 |
| 应用 OCEAN | 点击应用 | POST /v6/ocean/params | OCEAN 参数 |

**状态**: ✅ 读正常

---

### 11. Engineering (`/engineering`) — 工程链
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | GET /v6/engineering/modules | 模块列表 |
| 页面加载 | 自动 | GET /v6/engineering | 工程链数据 |
| 页面加载 | 自动 | GET /v6/recursive-map | 递归地图 |
| 编辑约束 | 输入+保存 | PUT /v6/engineering/constraints | 保存约束 |

**状态**: ✅ 全部正常

---

### 12. Sessions (`/sessions`) — 会话管理
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | GET /v6/sessions | 会话列表 |
| 页面加载 | 自动 | GET /v6/persistence | 持久化状态 |
| 页面加载 | 自动 | GET /v6/persistence/graphs | 持久化图 |
| 点击会话 | 用户点击 | GET /v6/session/{filename} | 会话详情 |
| 导入文档 | 上传文件 | POST /v4/ingest | 导入文档 |

**状态**: ✅ 全部正常

---

### 13. Settings (`/settings`) — 设置
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | GET /v6/rules | 规则列表 |
| 编辑规则 | 输入+保存 | PUT /v6/rules | 保存规则(name+conclusion+confidence) |
| 修改上下文 | 输入+保存 | PUT /v6/context/config | 上下文配置 |
| 修改参数 | 输入+保存 | PUT /v6/parameters | 参数配置(key+value) |

**状态**: ✅ 读取正常，⚠️ 编辑字段名需匹配

---

### 14. NotFound (`*`) — 404 页面
| 操作 | 触发 | API | 预期结果 |
|------|------|-----|---------|
| 页面加载 | 自动 | (无) | 显示 404 |

**状态**: ✅

---

## 三、前端 Hook 层

| Hook | 职责 | 数据源 |
|------|------|-------|
| useV6Gateway | 健康检查 + Provider + 路由 + 用量 (15s 轮询) | /v6/gateway/* |
| useWebSocket | WS 创建+收发 (ws_url 为空时跳过) | /v3/session |
| useSession | REST 会话操作 | /v3/session/* |
| useChat | 消息发送+历史 | useWebSocket |
| useV6Profile | 画像+追踪+ABC+Mind 复合加载 | /v6/profile + /v6/trace + /v6/abc + /v6/mind |
| useV6DeepChain | 深层链聚合 | /v6/relations + causal + behavior + engineering |
| useV6Graph | 对话图+对象+关系 | /v6/graph + objects + relations |
| useV6Pipeline | 管线状态 | /v6/pipeline |
| useV6Sessions | 会话列表+详情+导入 | /v6/sessions + /v4/ingest |
| useHealth | 健康心跳 | /v4/health |
| useContentScript | 浏览器插件桥接 | (浏览器 API) |
| useMediaQuery | 响应式布局 | (CSS) |

---

## 四、写操作全链路 (前端 → API → Gateway → LLM)

```
1. 配置 Key (Gateway Page)
   前端: PUT /v6/gateway/providers/{name} { api_key, base_url }
     → API: proxy → PUT http://127.0.0.1:8080/v1/admin/providers/{name}
       → Gateway: Register(cfg) + persistProviderToYAML(cfg)
         → 写入 gateway/provider.yaml ✅

2. 发送消息 (Chat)
   前端: POST /v3/session/{id}/message { content }
     → API: v3_send_message → post_event(EventRequest)
       → Engine: process_event → _llm_provider.generate()
         → SwitchGateway: POST /v1/chat/completions
           → DeepSeek: AI 回复
         ← 返回回复文本

3. 编辑规则 (Settings)
   前端: PUT /v6/rules { name, conclusion, confidence }
     → API: 更新内存规则存储

4. 编辑画像 (Profile)
   前端: PUT /v6/profile { dimension, value }
     → API: 更新 OCEAN 维度

5. 元认知扫描 (Meta Center)
   前端: POST /v6/meta/scan
     → API: Engine._meta.scan()

6. 版本回滚 (Meta Center)
   前端: POST /v6/versions/{category}/rollback { commit_id }
     → API: VersionControl.rollback()
```

---

## 五、错误处理 + 降级层

| 错误 | 前端处理 | 后端处理 |
|------|---------|---------|
| API 不可达 | servicesDown=true, 用 DEFAULT_PROVIDERS | — |
| Gateway 不可达 | swStatus.healthy=false, fallback 到 builtin | — |
| 401 未授权 | 自动带 Bearer dev-token | auth_middleware 放行 |
| LLM 调用失败 | 显示 error 消息 | 500 返回 |
| WebSocket 失败 | ws_url="" → 跳过 WS, 纯 REST | ws_endpoint 备用 |
| 构建错误 | tsc 编译失败 → Vite 不输出 | — |
