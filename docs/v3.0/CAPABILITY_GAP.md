# 当前实现能力报告

## 可以做什么

### 1. 摄入文档构建语义世界
- 88篇 Markdown → ObservationPool (91 bundles, 7000+ observations)
- 自动提取概念、关系、heading层级 → ConceptGraph + SemanticIndex
- 构建 9.8K SemanticObject + 5.4K RelationEdge
- 全部自动化，多次运行结果一致

### 2. 中文自然语言查询 → 结构化上下文
- 用户问 "有记忆吗" → jieba分词 → BGE语义匹配 → 定位到 "MemoryManager" 对象
- 渲染 world_view (design文本) + world_relation (关系边) → 注入 LLM context
- Multi-Perspective: primary(architecture, depth=2) + secondary(engineering, depth=1)
- Profile TrackA 每轮累积 (认知惯性/信任度/注意力锚点)

### 3. 对话树追踪
- DiscourseBlockTree: 每轮自动判断 continue/fork
- 树结构注入 LLM context: [Active Branch] + [Related Topics]
- 粘合度计算: BGE快速通道 + 9维公式灰区

### 4. 多Provider LLM
- GatewayLLMProvider → Switch → DeepSeek/LMStudio/OpenAI
- 直接 OpenAIProvider (DeepSeek, LMStudio)
- MockProvider (测试)

### 5. 语义提取 (四层降级)
- jieba: 中文实体+关系提取 (<10ms)
- Stanza: 依存句法分析 (~50ms)
- LMStudio: nemotron小模型JSON格式提取 (~500ms)
- DeepSeek: 云端最高质量 (~2s)

### 6. 测试覆盖
- 179 单元+集成测试, 19秒全量
- 端到端集成验证: world_view/profile/discourse_tree/slow_path 全部通过
- Session fixture: 5文档世界模型复用

### 7. CLI + TUI
- CLI: 13个命令 (status, inspect, search, event, health...)
- TUI: 9标签页 Textual dashboard (Dashboard/Observations/Hypotheses/Knowledge/Skills/World/Context/EventLog/Settings)

---

## 缺什么 (按优先级)

### P0 — 核心功能缺口 (影响端到端可用性)

| 项目 | 说明 | 影响 |
|------|------|------|
| **Switch Gateway 未启动** | GatewayLLMProvider已写,但Switch服务器未运行 | 只能用DeepSeek,无法切换Provider |
| **LMStudio提取未消费** | Slow Path路径已通,但LMStudio提取结果从未实际进入RelationSubstrate (需6+轮触发) | 提取四层只用了jieba |
| **CodeResolver无数据** | tree-sitter代码提取器就绪,但ObservationPool里没有代码块 | engineering视角=architecture视角,触发去重跳过 |
| **Stanza模型加载超时** | 代理环境下无法下载中文模型 | Tier2提取层跳过 |
| **KnowledgeResolver空** | 返回空字符串,无冻结知识查询 | 知识域空 |

### P1 — 设计承诺但未实现

| 项目 | 设计文档 | 代码行数 | 影响 |
|------|---------|---------|------|
| **元认知 (Metacognition)** | DESIGN_FULL_CONCEPT §4.3, DESIGN_SKILL_LAYER §7 | 0 | LLM无法反思自身决策 |
| **LLM Cognitive Tree** | DESIGN_MULTILAYER_LLM_COGNITIVE §4 | 0 | LLM缺少独立心智空间 |
| **Causal mechanism** | DESIGN_RELATION_SUBSTRATE Phase 4 | 0 | 5000+边全无因果解释 |
| **Code + Git evidence** | DESIGN_RELATION_SUBSTRATE Phase 5 | 0 | 关系无边版本/代码证据 |
| **Capability Space** | DESIGN_PERSPECTIVE_PLANNER §6 | 接口stub | 无能力空间视角 |
| **Runtime Advisor** | DESIGN_COGNITIVE_SCHEDULER §3 | 0 | 调度策略无自适应 |
| **Multi-Layer Memory** | DESIGN_00_OVERVIEW Phase 3 | 0 | 无Hot/Working/Engineering/Long-term分层 |
| **温度模型** | design_discourse_block_tree_v2 §2.2 | 0 | active/paused/cold/frozen未实现 |
| **TrackB 标签** | DESIGN_FULL_CONCEPT §6 | cold start | 用户画像只有TrackA |
| **SkillResolver** | DESIGN_SEMANTIC_OBJECT §3.3 | stub | 无技能查询 |
| **HeaderInjector因果KB** | design_discourse_block_tree_v2 §4.1 | 硬编码空dict | 代词消解弱 |
| **渐进式四级摘要** | design_discourse_block_tree_v2 §7 | 0 | 无v1→v2→v3→v4压缩 |
| **OpenClaw适配** | DESIGN_00_OVERVIEW Phase 2 | 0 | 无外部工具连接 |
| **评估体系** | DESIGN_00_OVERVIEW Phase 4 | 0 | 无信息密度/推理完整性/浪费率指标 |
| **前端 GUI** | DESIGN_FRONTEND | React源码存在但未对接 | 无Web界面 |
| **BGE模型更新** | DESIGN_SEMANTIC_WORLD_MODEL | BGE-small-zh (中文→中文) | 无跨语言embedding |

### P2 — 质量/工程缺口

| 项目 | 说明 |
|------|------|
| **长对话测试** | 无20+轮回溯验证 |
| **消融实验** | 未测试摘除各模块的效果 |
| **覆盖率报告** | coverage.py未运行 |
| **内存泄漏检查** | 无压力测试 |
| **Rust化核心路径** | 全Python, BGE编码+对象构建是瓶颈 |
| **Docker部署** | Dockerfile存在但未验证 |
| **API文档** | 无OpenAPI/Swagger |
