# TaskPlanningPage 业务流溯源 (2026-07-27)

> 基于前端源码逐行追踪，包含后端交互链路

## 一、架构总览

```
┌──────────────┐   GET/PUT    ┌─────────────────────┐
│ TaskPlanning │◄────────────►│ Backend              │
│    Page      │  /task-graph │ v3_session_api.py    │
│ (React x RF) │              │ data/task_graphs/    │
└──────┬───────┘              └─────────────────────┘
       │
       │ setTaskGraph / getState
       ▼
┌──────────────┐
│  taskStore   │ (Zustand, 内存)
│  taskGraph   │
└──────┬───────┘
       │ useTaskStore(s => s.taskGraph)
       ▼
┌──────────────────────────────────────┐
│ TaskPlanningPage — 状态分层         │
│                                     │
│ storeGraph ──useMemo──▶ rfNodes     │
│                         rfEdges     │
│                           │         │
│                   useState([...])   │──── 传给 TaskFlow ──▶
│                   useEffect 同步 ←── │                       │
│                                     │            useNodesState(initialNodes)
│  nodes ─────────── props ───▶ TaskFlow                      │
│                                ┌───── internal nodes 状态   │
│                                │  useNodesState             │
│                                │  onNodesChange (内部)      │
│                                │  highlightedNodes          │
│                                └────────────────────────────│
└─────────────────────────────────────────────────────────────┘
```

**致命问题**: 两组 nodes 状态——`TaskPlanningPage.nodes` 和 `TaskFlow 内部 useNodesState`——互不同步。

## 二、完整生命周期 (逐行追踪)

### 2.1 页面挂载

```
1. TaskPlanningPage mount
   storeGraph = null (taskStore初始值)                  // 327行
   sessionId = useChatStore(s => s.sessionId)           // 331行
   loaded = false                                        // 336行

2. useEffect #1: 加载数据                               // 337-348行
   getTaskGraph(sessionId) → GET /v3/session/{id}/task-graph
   ↓ 响应 { nodes: [...], edges: [...] }
   convertToTaskGraph(apiNodes) → TaskGraph对象
   useTaskStore.getState().setTaskGraph(tg)            // 存到 store
   setLoaded(true)                                      // 标记加载完成

3. storeGraph 变化 → rfNodes 重算                      // 351-352行
   rfNodes = toReactFlowNodes(storeGraph.nodes)
   = [{ id:'pcr_0', position:{x:0,y:0}, data:{...} }, ...]

4. useEffect #2: 同步 rfNodes → nodes (BUG)           // 357行
   setNodes(rfNodes)  ← 覆盖nodes状态
   setEdges(rfEdges)
   ⚠️ 此后每次 rfNodes 变化都触发此覆盖！

5. TaskFlow 挂载条件: loaded === true                    // 531行
   <TaskFlow nodes={nodes} edges={edges} .../>

6. TaskFlow 内部:
   useNodesState(initialNodes) → 内部nodes状态          // 259行
   useEdgesState(initialEdges) → 内部edges状态
   ⚠️ initialNodes 只在首次渲染时使用
   ⚠️ 后续 prop 变化不会更新内部状态 (useState语义)
```

### 2.2 用户拖动节点

```
7. 用户点击节点 → 拖动
   ReactFlow 内部: onNodesChange({type:'position', id, position})
   → TaskFlow.handleNodesChange(changes)               // 295行
   → onNodesChange(changes) ← useNodesState 的 handler
   → 内部 nodes 状态更新 (位置保存到内部状态)
   ✅ 画布上节点移动到新位置

8. ...但 TaskPlanningPage.nodes 没更新！
   handleNodesChange 只调了内部 handler
   没有调 TaskPlanningPage 的 setNodes
   TaskPlanningPage.nodes 仍是旧值

9. 触发 re-render (任何原因):
   rfNodes 不变 (storeGraph 没变)
   useEffect #2 不触发 (rfNodes 引用没变)
   nodes 状态没被覆盖 ← 这次OK
   ✅ 拖拽位置保持
```

### 2.3 点击 "添加节点"

```
10. handleAddNode() → tfRef.current.addNode(rfNode)    // 427行
    → TaskFlow 内部: setNodes(nds => [...nds, rfNode])  // 264行
    ✅ 画布上出现新节点

11. 同时: useTaskStore.setState({taskGraph:{ ... }})    // 432行
    ← storeGraph 更新!
    → rfNodes 重算 (新数组引用)
    → useEffect #2 触发: setNodes(rfNodes)   
    ⚠️ rfNodes 是从 store 计算的固定位置!
    ⚠️ TaskPlanningPage.nodes 被覆盖为计算值
    ⚠️ 新节点的随机位置丢失!
    ⚠️ 之前所有拖拽位置丢失!
    ⚠️ 传递给 TaskFlow 的 nodes prop 变了

12. TaskFlow 收到新 nodes prop:
    useNodesState 忽略 (useState 语义)
    内部 nodes 状态不变 ← 新旧状态独立
    BUT: highlightedNodes 用内部 nodes
    画布上显示仍是内部状态 ← 看起来"OK"

13. 下一次 re-render:
    handleNodesChange 用内部 handler
    但如果选了节点 → highlightedNodes 重建新数组
    → ReactFlow 收到新 nodes 引用
    → ReactFlow 对比 diff → 可能重置事件处理器
``` 

### 2.4 Auto-save

```
14. useEffect #3: auto-save                              // 363-369行
    dependencies: [storeGraph, sessionId]
    每当 storeGraph 变化 → PUT /task-graph
    debounce 2秒

15. saveTaskGraph 回调完成:
    不修改 storeGraph ← 不会触发 rfNodes 重算
    ✅ 不引起额外重置
```

### 2.5 切换页面再回来

```
16. TaskPlanningPage unmount
    → TaskFlow 销毁 (内部 nodes 状态丢失)
    → taskStore 保留 (Zustand 在内存)

17. TaskPlanningPage remount
    → loaded 重置为 false → useEffect #1 重跑
    → GET /task-graph → 获取后端存储的最新数据
    → setTaskGraph → storeGraph 更新 → rfNodes 重算
    → useEffect #2: setNodes(rfNodes)
    → TaskFlow 挂载 with correct initialNodes
    ✅ 数据从后端恢复
```

## 三、问题根因矩阵

| # | 现象 | 根因 | 代码位置 |
|---|------|------|---------|
| 1 | 拖动松手回弹 | useEffect #2 每次 rfNodes 变化时 setNodes(rfNodes) 覆盖位置 | TaskPlanningPage:357 |
| 2 | 添加节点不显示 | handleAddNode 更新 store → rfNodes 重算 → useEffect #2 覆盖 nodes | TaskPlanningPage:357+432 |
| 3 | 连线操作无效 | handleConnect 只更新 store, 不更新 TaskFlow 内部 edges | TaskPlanningPage:397 |
| 4 | 删除偶尔有效 | Backspace → handleNodesDelete → 更新 store + TaskFlow 内部状态 | 两者几乎同时 |
| 5 | "瞬间可用" | 在 useEffect #2 两次触发之间的窗口期, 拖拽位置尚未被覆盖 | 时序问题 |
| 6 | 切页面数据丢失 | taskStore 不持久化, GET 重拉是正确的, 但 PUT 可能没保存 | 架构问题 |

## 四、后端链路

```
GET  /v3/session/{id}/task-graph
  → 读 data/task_graphs/{id}.json (优先)
  → 回退: 从 v3_sessions.json 的 messages 中提取

PUT  /v3/session/{id}/task-graph
  → 写 data/task_graphs/{id}.json

POST /v3/session/{id}/message (chat)
  → Phase 5: BlueprintEngine.build() → task_graph
  → 另存 data/task_graphs/{id}.json
```

## 五、状态流图 (完整)

```
                    ┌──────────────┐
                    │   Backend    │
                    │ task_graphs/ │
                    └──────┬───────┘
                           │ GET (on mount)
                           ▼
              ┌─────────────────────┐
              │   taskStore.graph   │ ← Zustand
              │   (TaskGraph类型)    │
              └──────────┬──────────┘
                         │ useMemo (每次graph变化)
                         ▼
              ┌─────────────────────┐
              │      rfNodes       │ ← 计算值 (固定网格位置)
              │      rfEdges        │
              └──────────┬──────────┘
                         │ useEffect (⚠️ 每次rfNodes变化)
                         ▼
              ┌─────────────────────┐
              │  TaskPlanningPage   │
              │  nodes (useState)  │ ← 被 rfNodes 覆盖
              │  edges (useState)  │
              └──────────┬──────────┘
                         │ props
                         ▼
              ┌─────────────────────┐
              │     TaskFlow        │
              │  useNodesState(...) │ ← 内部独立状态
              │  internal nodes     │ ← 拖拽/添加在这里
              └─────────────────────┘

  ⚠️ 两组 nodes 互不同步:
     - TaskPlanningPage.nodes → 从 store重算, 走 useEffect 覆盖
     - TaskFlow internal nodes → 用户操作, 但父组件不知
```

## 六、修复方案

**根本问题**: useEffect #2 (357行) 每次 rfNodes 变化都覆盖 nodes。

**方案**: 删掉 useEffect #2，只在初始加载时设置 nodes 一次。

```diff
- useEffect(() => { setNodes(rfNodes); setEdges(rfEdges); }, [rfNodes, rfEdges]);
+ // REMOVED — see fix below
```

改为在 `loaded` 变为 true 且是首次时设置：

```typescript
// In the fetch useEffect:
useEffect(() => {
  if (sessionId && !loaded) {
    getTaskGraph(sessionId).then(data => {
      const apiNodes = data.nodes || [];
      if (apiNodes.length > 0) {
        const tg = convertToTaskGraph(apiNodes);
        if (tg) {
          useTaskStore.getState().setTaskGraph(tg);
          // 直接设置 nodes/edges 一次
          setNodes(toReactFlowNodes(tg.nodes));
          setEdges(toReactFlowEdges(tg.nodes));
        }
      }
      setLoaded(true);
    });
  }
}, [sessionId, loaded]);
```

同时**删除** rfNodes/rfEdges 的 useMemo + 删除 useEffect #2。
这样 nodes 状态只在首次加载时设置一次，之后完全由 ReactFlow 内部状态管理。
