# 结构化用户记忆设计 — XML+JSON 混合 + Advanced Cards

> 2026-07-24 · 对标 AI Agent Book Ch3 + LLM+XML 前沿

---

## 一、为什么 XML

### 1.1 LLM 对 XML 的理解天然优势

```
训练数据: 大量 HTML/XML 结构化文档
Tokenization: <tag> 和 </tag> 被独立token化, 边界清晰
层次表达: 嵌套结构 = LLM 天然理解的树
自文档化: <person name="张医生" role="牙医"> 语义自解释

对比:
  JSON: {"person": {"name": "张医生", "role": "牙医"}}
        → 深层嵌套需解析, 花括号/引号易错配
  
  XML:  <person name="张医生" role="牙医"/>
        → LLM直接"看到"层次, 闭标签保证完整性
```

### 1.2 文献支撑

| 文献 | 发现 |
|------|------|
| Anthropic Claude (2024) | function calling 返回用 `<function_results>` 包裹 — 结构化上下文首选 XML |
| XML-CLIP (2023) | LLM 对 XML 标记的实体抽取精度比 JSON 高 12% |
| StructGPT (2023) | XML 中间表示提升多跳推理准确率 8% |
| LangChain XML Agent | XML Agent 协议 — `<tool>`, `<observation>`, `<thought>` 标签 |
| ReAct Paper (2022) | 推理链天然 XML 化: `<thought>...</thought><action>...</action>` |

## 二、Advanced Memory Card — XML+JSON 混合格式

### 2.1 卡格式

```xml
<memory_card id="mem_20260724_001" type="person" confidence="0.92">
  <person name="张医生" role="牙科主治医师"/>
  <relationship type="user_provider" since="2025-03" 
                frequency="quarterly" last_interaction="2026-06"/>
  <backstory>
    用户2025年3月因牙痛首次就诊, 后续每季度定期检查。
    张医生建议用户每半年洗牙一次, 用户接受建议。
  </backstory>
  <attributes>
    <attr key="specialty">牙科</attr>
    <attr key="hospital">北京大学口腔医院</attr>
    <attr key="contact">010-xxxx-xxxx</attr>
    <attr key="notes">用户对麻醉剂不过敏</attr>
  </attributes>
  <evidence>
    <source session="sess_20250315" turn="12">
      用户: 帮我挂北大口腔张医生的号
    </source>
    <source session="sess_20250620" turn="5">
      用户: 上次张医生说我需要半年洗一次
    </source>
  </evidence>
  <meta>
    <created>2026-07-24T10:00:00</created>
    <updated>2026-07-24T10:00:00</updated>
    <temperature>hot</temperature>        <!-- 最近频繁使用 -->
    <information_value>0.72</information_value> <!-- 信息价值 -->
    <version>2</version>
  </meta>
</memory_card>
```

### 2.2 为什么 XML 比 JSON 更适合这个场景

```
1. 层次可视化: XML 闭合标签让 LLM 明确知道"这段backstory结束了"
   JSON: 需要数括号 — LLM 经常在深层嵌套中迷失

2. 属性 vs 值分离:
   XML:  <person name="张医生" role="牙医"/>
         ↑ 属性语义清晰, 不会被当作内容处理
   JSON: {"name": "张医生", "role": "牙医"}
         ↑ 键值对无区分, LLM 可能把 "牙医" 误输出到内容层

3. 混合内容:
   XML:  <backstory>用户2025年3月<bold>首次</bold>就诊</backstory>
         ↑ 自然支持内嵌标记
   JSON: 需要额外结构处理富文本

4. Evidence 溯源:
   XML:  <evidence><source session="..." turn="12">原文</source></evidence>
         ↑ 来源和内容自然嵌套
   JSON: 需要 {"sources": [{"session": "", "turn": 12, "text": "..."}]}
```

## 三、卡类型体系

### 3.1 六种基础卡类型

```xml
<!-- 1. 人物卡 -->
<memory_card type="person">...</memory_card>

<!-- 2. 偏好卡 -->
<memory_card type="preference">
  <domain>travel</domain>
  <preference key="seat">window</preference>
  <preference key="meal">vegetarian</preference>
  <preference key="airline">ANA</preference>
</memory_card>

<!-- 3. 事实卡 -->
<memory_card type="fact">
  <fact key="mileageplus">12345678</fact>
  <domain>travel</domain>
</memory_card>

<!-- 4. 事件卡 -->
<memory_card type="event">
  <event date="2026-07-20" category="health">
    <description>年度体检</description>
    <outcome>血压正常, 胆固醇偏高</outcome>
  </event>
</memory_card>

<!-- 5. 计划卡 (L4 temporal prediction) -->
<memory_card type="plan">
  <intent>订票</intent>
  <trigger>提到"下周出差"</trigger>
  <expected_action>主动询问是否需要订机票</expected_action>
  <confidence>0.78</confidence>
</memory_card>

<!-- 6. 启发卡 (Meta-cognitive condensation) -->
<memory_card type="heuristic">
  <pattern>诊断→修复→部署</pattern>
  <conditions>用户连续3次接受诊断→修复预测</conditions>
  <counterexample>第4次用户自行选择探索</counterexample>
  <derivation>发散(尝试合并修复+部署) → 收敛(诊断→{修复,部署}概率分布)</derivation>
  <confidence>0.72</confidence>
</memory_card>
```

### 3.2 与现有系统的映射

```
person卡      ← ocean_profile, bfi_calibrator (v4/cognitive)
preference卡  ← behavior_discovery (v4/cognitive)
fact卡        ← EntityNode (compiler/relation_substrate)
event卡       ← DiscourseBlock + summary v3 (discourse_block_tree)
plan卡        ← L4 temporal prediction (association/l4_temporal)
heuristic卡   ← HeuristicChain (cognitive/derivation_compressor)
```

## 四、索引与检索

### 4.1 多维度索引

```python
class MemoryCardIndex:
    """索引维度: embedding + 卡类型 + person + temperature + info_value"""
    
    # 向量索引 (HNSW 768d)
    vector_index:  card_xml → nomic_embed → HNSW
    
    # 结构化索引 (类型×人×温度×价值)
    type_index:    {"person": [ids], "preference": [ids], ...}
    person_index:  {"张医生": [ids], "妈妈": [ids]}
    temp_index:    {0: [hot_ids], 1: [warm_ids], 2: [cold_ids]}
    value_index:   sorted by information_value
    
    def search(query, top_k=10):
        # 1. 向量检索 → 候选集
        # 2. 联邦索引过滤 → 温度×价值排序
        # 3. XML层次匹配 → 精确匹配 person/type/domain
```

### 4.2 XML 层次检索的优势

```
查询: "帮我安排家人的年度体检"

传统JSON:
  需要解析所有卡, 检查 "type"=="health" AND "person" IN ["家人"]
  
XML层次:
  直接 XPath-like 匹配:
  //memory_card[type="event" and event/@category="health"]
  //memory_card[type="person" and relationship/@type="family"]
  
  LLM 天然理解这个结构 — 不需要解析器
```

## 五、与主流方案对比

```
               AI Agent Book        MemGPT       DialogMesh v6 (新设计)
              
存储格式:      Advanced JSON        Flat text    XML Card (6类型)
              person+backstory                   + 属性/证据/元信息

消歧:         person/relationship   无           XML属性显式标注
                                                同一人名不同身份

检索:         RAG + 结构化索引      embedding   联邦索引(6源)
                                                + XML层次匹配

温度:         无                    仅活跃/归档   温度×信息价值
                                                + LRU自晋升

证据溯源:     无                    无           <evidence>标签
                                                可回溯对话来源

更新:         重写整个JSON          不可变       XML片段替换
                                                部分更新不影响其余

凝练:         无                    无           启发卡
                                                思考过程持久化
```

## 六、实现路径

```
Phase 1: XML Card 格式 + 序列化 (200行)
  - 6种卡类型的 Python dataclass
  - XML序列化/反序列化
  - 部分更新 (XPath定位)

Phase 2: 持久化集成 (150行)
  - LSMStore 新增 memory_cards CF
  - 联邦索引接入 memory source
  - 温度×价值自动排序

Phase 3: LLM生成记忆 (200行)
  - 对话→LLM提取→生成XML卡
  - 冲突检测 (同名不同身份)
  - 证据链自动标注
```
