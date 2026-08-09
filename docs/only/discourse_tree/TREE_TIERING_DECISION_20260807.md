# 对话树/图树化 — OS 式内存↔磁盘分层接线拍板（2026-08-07）

> 状态: 拍板（设计出处确认 + gap 定位 + 施工清单）
> 触发: 图谱页"交互图是单链，没做树图化"——实测发消息后 /v6/graph
> 会出树（child_of/parent_of 层级边），但历史会话/重启后全部退化成
> 20 节点会话链兜底。

---

## 一、用户判断（已确认正确）

> "树整体是内存态的，这是和内存一个类型策略：命中了拿取，回持久化了则
> 回入，新启动的时候也会预先加载，退出了也会持久化回去。参考操作系统的
> 方式（虚拟内存 page-in/page-out）。"

== 与"内存"同一套策略：Hot/Warm/Cold 分层 + 命中/回热/预加载/退出落盘。

## 二、设计出处（已有，非新增）

`docs/only/context/DESIGN_FULL_READ_20260803.md`：

### §6.1 四层结构（分层工作记忆，v3 ENGINEERING_CONTEXT_MANAGER）
```
Hot Layer  (容量 3)  — 完整轮次记录，内存 OrderedDict
Warm Layer (容量 7)  — 单轮摘要，SQLite
Cool Layer (容量 20) — 多轮合并摘要，SQLite
Cold Layer           — 仅索引，gzip JSONL
降级链: Hot→Warm→Cool→Cold
回热:   rehydrate_cold(session_id, topic_id) → Cold→Cool（精确匹配）
```

### §12.4 分层存储写入流（ENGINEERING_PERSISTENCE）
```
写入: HOT→TieredStorageManager.put_hot(内存) / WARM·COOL→SQLite /
      COLD·FROZEN→archive_warm_to_cold(归档文件)
读取: Hot 命中返回 → Warm 命中并异步 put_hot → Cold 命中并
      rehydrate_cold_to_warm + put_hot
```

→ **用户描述的 OS 式策略在设计里已存在**（§12.4 正是"命中拿取/回入"）。

## 三、现状 gap（实测定位）

| 项 | 实测 | 问题 |
|---|---|---|
| DiscourseBlockTreeManager | 只有 `feed()/ingest_turn()`，**无 save/load/serialize** | 树纯内存态，重启即丢 |
| state.json | 只存 `current_session/provider/key/model` | 不含任何树 |
| TieredStorageManager | `core/agent/persistence/tiered_storage.py` 存在（H/W/C 迁移完整） | **从未接入 discourse/图路径** |
| kernel_graph | 内存无块 → 兜底 v3_sessions 20 会话链（sequence 边） | 链 ≠ 树，误导"没做树图化" |
| 会话选择 | kernel 用 CLI `get_session()`（进程全局） | 与前端当前会话错位 |
| 消息链路 | `user_message` → DiscourseSubscriber → feed ✅（实测 1 条消息出 3 块树） | 链路通，缺持久化 |

## 四、拍板（OS 式分层，对齐 §12.4）

```
Hot   = 内存 blocks（feed 时构建，活跃会话）
Warm  = discourse_trees/{sid}.json（序列化树，定时/退出落盘）
Cold  = v3_sessions.json 原文（源真理，冷页换入=重建）

page-in: kernel_graph(sid) → Hot 有 → 直接返回
         → 无 → Warm 读入并回热（异步 put_hot）
         → 无 → Cold 重建（feed 该会话 user 消息）
page-out: feed() 后 debounce 落 Warm；退出/定期把活跃树写盘
预加载:   启动 page-in 最近活跃会话（warm_start）
```

### 附加拍板
1. **kernel_graph(sid)**：支持 `?sid=`，前端传当前会话；三级取数，
   全空 → 空图 + `empty_reason`（**删除会话链兜底**）
2. 节点类型树化：根块 → `session`，子块 → `concept`；边 `child_of`/
   `parent_of` + `reference`（cross_ref）
3. 树整体共享（B 内核单会话 blocks 已知限制）：页面定位为"当前会话对话树"，
   多会话隔离列为后续（kernel 升级）

## 五、施工清单
1. `discourse_block_tree/manager.py`：`export_blocks()/import_blocks()`
   （id/parent/child_ids/summary/raw_text/temperature/cross_refs/entities）
2. engine 接线：`_persist_state` 写 `discourse_trees/{sid}.json`；
   atexit/shutdown 落盘；启动 warm_start 预加载
3. `kernel_graph(sid)` + `kernel_discourse_tree(sid)`：Hot→Warm→Cold 取数，
   删链兜底；`stubs_api.py` 路由加 `?sid=` Query
4. 前端：`v6.ts getGraph(sid?)` + ConversationGraphPage 传当前会话 sid
5. 验证：重启后 /v6/graph?sid=xxx 仍出树（不再链）；发消息即时出树；
   空会话返回空图 + 原因

## 五续、施工完成（2026-08-08 实测）

- ✅ manager: `export_blocks(session_id=)/import_blocks()`（含结构/文本/
  entities/cross_refs/session 标签）+ `get_block_relations` 增强
  （raw_text 兜底 atomic_units、summary 用 `ProgressiveSummary.get_best()`）
- ✅ engine: `_persist_discourse_tree(force=)/_load_discourse_tree()/
  _warm_start_discourse()`；feed 后自动 page-out（3s debounce）；
  bootstrap 挂载后重挂 hook（registry 会重建 discourse_tree 覆盖 __init__ 实例）
- ✅ `kernel_graph(sid)/kernel_discourse_tree(sid)`: Hot→Warm→Cold 三级取数；
  会话隔离（块打 `_session_id` 标签 + `_blocks_for` 过滤）；
  空 → 空图 + `empty_reason`；删除了 v3_sessions 会话链兜底
- ✅ 路由 `/v6/graph|discourse-tree?sid=`（fastapi Query）
- ✅ 前端: `getGraph(sid?)/getDiscourseTree(sid?)` + 图谱页传当前聊天会话
  （`?sid=` URL 兜底）+ 无 sid 时后端默认最近有内容会话
- ✅ 验证: 冷重建出树（2 节点 1 边）→ Warm 完整落盘 → 重启 Warm 换入
  （不再链）→ 空会话空图 + 原因；UI 30/30 + 后端 73/73 绿

### 踩坑记录（防复发）
1. registry `resolve_all()` 用工厂重建 `_discourse_tree` → hook 必须
   bootstrap 挂载后重挂（不能在 __init__ 只挂一次）
2. `Remove-Item -LiteralPath *.json` 不展开通配符（测试清理坑）
3. 冷重建连续 feed <3s 只落第一块 → `force=True` 结束强制落盘
4. `~/.dialogmesh` 有 ACL 权限坑（Errno 13）→ Warm 默认 `data/discourse_trees/`
5. 末位会话可能是无消息空壳 → 默认取"最近有内容会话"

## 六、哲学对齐
```
A17 记录永不可删:  Cold = 原文，Warm 是投影，可重建可恢复
A18 参数自适应:     分层阈值（Hot 容量/落盘频率）可配置
G10 分层存储:       discourse 树正式接入 tiered 体系（此前只接 task_graph）
A2 递归缩放:        树图 = 对话的缩放投影，冷热决定投影精度
```
