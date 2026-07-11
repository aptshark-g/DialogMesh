# Tiered Syntactic Parser：三层递进句法分析

> 三层递进精炼管道。每一层输出同一格式 ParsedClause，上层结果作为下层的种子输入。
> 不是三个独立解析器——是一个递进精炼管道。

> 版本: v1.0 | 日期: 2026-07-11

---

## 目录

1. 为什么需要三层
2. 三层架构
3. Tier 1: SyntacticDecomposer v2（规则）
4. Tier 2: spaCy + Benepar 协同
5. Tier 3: LLM + Schema Guard（神经符号）
6. 级联协同：上层输出如何作为下层输入
7. 与 Observation Compiler 的关系
8. 各方案评估

## 1. 为什么需要三层

单一方案无法同时满足延迟和准确率：

| 方案 | 延迟 | 准确率 | 瓶颈 |
|:---|:---|:---|:---|
| 纯规则 | <5ms | ~75% | 词典覆盖率有限，无法处理未登录词和复杂句式 |
| spaCy 依存分析 | ~30ms | ~92% | 单一路径，中文准确率低于英文 |
| LLM | ~500ms | ~97% | 延迟太高，不能每轮调用 |

三层递进：规则先跑（<5ms，覆盖 75% 常见句式），置信度不够升级到 spaCy（~30ms），
再不够升级到 LLM（~500ms，仅歧义 case）。最终 97% 覆盖率，加权平均延迟 ~10ms。

## 2. 三层架构

`
输入文本
  |
  v
Tier 1: SyntacticDecomposer v2（规则，<5ms）
  |  confidence > 0.7 -> 返回
  |  confidence < 0.7
  v
Tier 2: spaCy + Benepar 协同（~30ms，可选）
  |  confidence > 0.85 -> 返回
  |  confidence < 0.85 或多主语/歧义
  v
Tier 3: LLM + Schema Guard（~500ms）
  |  Schema Guard 验证 + 硬约束注入
  v
  返回高置信度 ParsedClause
`

关键：每一层输出同一格式 ParsedClause，上层结果直接传给下层当种子。

## 3. Tier 1: SyntacticDecomposer v2（规则）

零依赖，中英双语词典，小于 5ms。

能力：否定检测（30+ 词）、不确定检测（15+ 词）、祈使检测（20+ 词）、
谓语提取（七个动词类别 80+ 词）、宾语提取、实体提取（CamelCase + 关键词）。

触发升级条件：谓语未匹配、否定+不确定同时出现、多连词检测。

## 4. Tier 2: spaCy + Benepar 协同

spaCy 提供依存句法（谁是什么角色），Benepar 提供成分句法（短语边界在哪）。

spaCy 单独：add(ROOT), monitoring(dobj), Gateway(pobj)
Benepar 单独：(S (VP (VB add) (NP monitoring)) (PP to (NP the Gateway)))

协同：VP 边界取 Benepar 的 VP 子树，根动词取 spaCy 的 ROOT。
predicate=add, object=monitoring to the Gateway。置信度 0.92（两个模型同时确认）。

中文场景：Benepar 暂不支持中文。Tier 2 中文用 Stanza 替代 spaCy（Stanza 自带依存+成分句法）。

## 5. Tier 3: LLM + Schema Guard（神经符号）

仅当 Tier 2 无法确定时触发。

Prompt 注入 Tier 1/2 已解析的部分作为种子。注入硬约束（谓语必须在 PREDICATE_DICT 中）。

Schema Guard 验证：谓语必须在词典中、否定句不能有 create 意图、主谓宾必须非空。
这是神经符号的核心：LLM 做神经部分，Schema Guard 做符号约束。

## 6. 级联协同：上层输出作为下层输入

每层输出均为同一 ParsedClause 结构。上层结果不是丢弃——是传给下层作为提示种子。

`
Tier 1 输出: ParsedClause(predicate=add, confidence=0.55)
  -> Tier 2 收到: hint_predicate=add, 在此基础上做依存+成分分析
  -> Tier 2 输出: ParsedClause(predicate=add, object=monitoring..., confidence=0.92)
     -> 置信度达标，不再升级
`

这减少了 Tier 2 和 Tier 3 的搜索空间——它们不需要从零开始解析。

## 7. 与 Observation Compiler 的关系

Observation Compiler 是 TiredParser 的唯一调用方。

`
Event IR -> TieredParser.parse(text) -> ParsedClause
  ParsedClause.predicate -> Observation ActionType
  ParsedClause.object -> Observation Entity
  ParsedClause.negation -> Observation.modifiers[negated]
  ParsedClause.imperative -> Observation.modifiers[imperative]
  ParsedClause.confidence -> Observation.confidence
`

Observation Compiler 不关心内部用了哪一层解析——它只拿到最终的结构化结果。

## 8. 各方案评估

| 方案 | 纳入？ | 原因 |
|:---|:---|:---|
| spaCy 依存句法 | Tier 2 主力 | 主谓宾直接可用，14MB 轻量 |
| Benepar 成分句法 | Tier 2 协同 | 提供 VP/NP 边界，和 spaCy 互补 |
| Stanza | Tier 2 中文备选 | 中文准确率高于 spaCy，自带成分句法 |
| SyntacticDecomposer v2 | Tier 1 主力 | 零依赖，中英双语 |
| Schema Guard | Tier 3 神经符号 | LLM + 硬约束验证 |
| DecVAE 语法-语义解耦 | 不纳入 | 研究概念，无可部署工具 |
| CYKNN 神经符号解析 | 不纳入 | 论文级，无生产实现 |
| nlpgraph | 不纳入 | TypeScript，不兼容 Python |
| grammaCy | 不纳入 | 轻量规则，不如我们自己的 v2 可控 |

---

> 三层递进管道。Tier 1 覆盖 75% 常见句式（<5ms），Tier 2 覆盖 92%（~30ms），
> Tier 3 覆盖剩余 3% 的歧义case（~500ms）。加权平均延迟 ~10ms。
