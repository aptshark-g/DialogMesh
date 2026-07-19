# DialogMesh v6 — 网状业务链设计 · 第十章：子图——跨链通信与元认知专属上下文

> 版本: v1.0 | 日期: 2026-07-19
>
> 子图不是对话树的附庸——它是跨链通信的核心织物。
> 元认知需要自己的子图，对话树需要自己的子图，两者数据源相同、视角不同。

---

## 1. 子图的本质：不是数据，是视角

```mermaid
graph TD
    subgraph DATA["共享数据层"]
        DT["对话树"]
        BHV["行为链"]
        ASSOC["关联链"]
        ENG["工程链"]
        PROFILE["画像/惯性"]
        PARAM["参数注册表"]
        META_LOG["元认知日志"]
    end
    
    subgraph SUBGRAPHS["子图层 (视角不同)"]
        DT_SG["对话树子图<br/>目的: 生成回复<br/>数据: 当前话题+关联块<br/>视角: 用户当前问题"]
        META_SG["元认知子图<br/>目的: 审核+复盘<br/>数据: 修改前后+多链证据<br/>视角: 系统质量+一致性"]
    end
    
    DT --> DT_SG
    BHV --> DT_SG
    ASSOC --> DT_SG
    PROFILE --> DT_SG
    
    DT --> META_SG
    BHV --> META_SG
    ASSOC --> META_SG
    ENG --> META_SG
    PROFILE --> META_SG
    PARAM --> META_SG
    META_LOG --> META_SG
    
    DT_SG --> LLM["LLM 回复生成"]
    META_SG --> META_LLM["LLM 元认知审核"]
```

---

## 2. 对话树子图 (已有, 链01 §4)

```
目的: 为 LLM 生成回复提供上下文
视角: 当前用户问题的局部视野
数据源:
  D 域 (对话树): 当前话题块 + 关联块 (水波展开)
  K 域 (工程): 约束 + 模式
  B 域 (行为): 修正检测 + 需求建议
  P 域 (画像): 偏好 + 风格
  F 域 (子图反馈): OCEAN + MBTI

令牌分配: D:40%, K:20%, B:15%, R:10%, P:10%, F:5%
```

---

## 3. 元认知子图 (新)

### 3.1 目的与视角

```
目的: 为 LLM 元认知审核/复盘提供上下文
视角: 系统质量 + 多链一致性 + 修改效果

与对话树子图的关键区别:
  对话树子图: 窄而深 → 聚焦当前话题, 高质量细节
  元认知子图: 宽而浅 → 覆盖多链, 摘要级证据, 找矛盾
```

### 3.2 数据源与权重

| 域 | 内容 | 权重 | 说明 |
|----|------|:---:|------|
| **M (Meta)** | 元认知自身操作历史 | 15% | 上次做了什么决定? 对了还是错了? |
| **V (Version)** | Git 版本控制 diff | 25% | 修改前后的完整对比 (复盘核心) |
| **E (Evidence)** | 多链证据汇总 | 30% | 关联链边/行为模式/工程约束的一致性 |
| **I (Inertia)** | 惯性权重图 | 15% | 哪些惯性正在被打破? |
| **P (Profile)** | 用户画像摘要 | 10% | 用户偏好 → 影响审核标准 |
| **Q (Question)** | 当前审核对象 | 5% | 正在审核的具体条目 |

### 3.3 令牌分配

```
M 域 (操作历史):   15%  → 最近 10 条决策摘要
V 域 (版本 diff):   25%  → 修改前后的关键指标对比
E 域 (多链证据):   30%  → 各链对当前审核对象的验证/矛盾
I 域 (惯性):       15%  → 受影响的惯性模式 (权重变化)
P 域 (画像):       10%  → OCEAN 摘要 + 修正历史
Q 域 (问题):        5%  → 审核对象原文
─────────────────────────────
Total: 100% (默认 2000 tokens)
```

---

## 4. 子图的双向流动

```mermaid
sequenceDiagram
    participant DT_SG as 对话树子图
    participant META_SG as 元认知子图
    participant DATA as 共享数据层
    participant LLM as LLM
    
    Note over DT_SG: 生成回复时
    DT_SG->>DATA: 读取: 对话树/行为/关联/画像
    DATA-->>DT_SG: 当前话题上下文
    DT_SG->>LLM: 生成回复
    
    Note over META_SG: 审核时
    META_SG->>DATA: 读取: V域(版本diff)+E域(多链证据)+I域(惯性)
    DATA-->>META_SG: 修改前后对比+各链验证
    META_SG->>LLM: 审核判定
    
    LLM-->>META_SG: verdict + recommendation
    META_SG->>DATA: 写入: 元认知日志+版本控制+惯性更新
    
    Note over DT_SG: 下一轮对话
    DT_SG->>DATA: 读取: 含元认知更新后的数据
    Note over DT_SG: 元认知的结果已融入各链
```

---

## 5. 子图编译器——统一接口

```python
class SubgraphCompiler:
    """编译跨域子图——支持多种视角"""
    
    def compile_dialogue_subgraph(self, intent: Intent, budget: int) -> CrossDomainContext:
        """对话树子图: 为回复生成"""
        domains = {
            "D": self._get_discourse_blocks(intent, budget * 0.40),
            "K": self._get_engineering_context(intent, budget * 0.20),
            "B": self._get_behavior_signals(intent, budget * 0.15),
            "R": self._get_relation_context(intent, budget * 0.10),
            "P": self._get_profile_summary(budget * 0.10),
            "F": self._get_ocean_feedback(budget * 0.05),
        }
        return self._assemble(domains, budget)
    
    def compile_meta_subgraph(self, review_target: ReviewTarget, budget: int) -> MetaContext:
        """元认知子图: 为审核/复盘"""
        domains = {
            "V": self._get_version_diff(review_target, budget * 0.25),
            "E": self._get_multi_chain_evidence(review_target, budget * 0.30),
            "M": self._get_meta_operation_history(budget * 0.15),
            "I": self._get_inertia_impact(review_target, budget * 0.15),
            "P": self._get_profile_summary(budget * 0.10),
            "Q": self._get_review_target_detail(review_target, budget * 0.05),
        }
        return self._assemble(domains, budget)
    
    def compile_retrospection_subgraph(self, retro_target: str, budget: int) -> RetroContext:
        """复盘子图: 为深度回溯 (预留)"""
        # 未来: 包含更长时间跨度的 before/after 对比
```

---

## 6. 子图在各链中的角色

```mermaid
graph TD
    subgraph CHAINS["9条业务链"]
        C01["链01: 对话树"]
        C02["链02: LLM回复"]
        C03["链03: 用户修改"]
        C04["链04: 元认知+持久化"]
        C05["链05: 行为链"]
        C06["链06: 关联链"]
        C07["链07: 工程链"]
        C08["链08: 画像"]
        C09["链09: 元认知"]
    end
    
    SG["子图编译器<br/>(跨链通信织物)"]
    
    C01 -->|"需要回复上下文"| SG
    C02 -->|"产出回复→回写"| SG
    C03 -->|"修改记录→版本控制"| SG
    C04 -->|"持久化数据→共享层"| SG
    C05 -->|"行为模式→证据"| SG
    C06 -->|"关联边→证据"| SG
    C07 -->|"约束→证据"| SG
    C08 -->|"惯性→证据"| SG
    C09 -->|"审核结果→回写"| SG
    
    SG -->|"对话树子图"| LLM1["LLM 回复"]
    SG -->|"元认知子图"| LLM2["LLM 审核"]
    SG -->|"复盘子图(预留)"| LLM3["LLM 复盘"]
```

---

## 7. 闭环判定

```
业务闭环 = 10 条链 + 1 个跨链子图 + 1 个开关网关

  9 条业务链: 覆盖认知推理全链路
  1 条子图: 跨链通信织物 (对话树视角 + 元认知视角)
  1 个网关: DialogMesh ↔ switch gateway

闭环标志:
  ✅ 用户输入 → 对话树子图 → LLM 回复
  ✅ LLM 回复 → 各链回写 → 惯性更新
  ✅ 系统异常 → 元认知子图 → 审核/复盘
  ✅ 用户修改 → 版本控制 → 元认知消费
  ✅ 元认知决策 → 回写各链 → 下次对话可见
  ✅ 全部通过 switch 网关 → Provider 透明切换
```

---

## 8. 路径归属

| 操作 | Fast | Async | Slow |
|------|:----:|:-----:|:----:|
| 对话树子图编译 | ✅ | | |
| LLM 回复生成 | ✅ | | |
| 元认知子图编译 | | ✅ | |
| LLM 审核调用 | | ✅ | |
| 复盘子图编译 | | | ✅ |
| 子图回写共享数据层 | | ✅ | |
| 版本控制写入 | ✅ | | |
