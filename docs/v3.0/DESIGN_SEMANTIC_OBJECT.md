# Semantic Object — v4 统一对象模型

> 版本: v3.0 | 日期: 2026-07-16
> 状态: Draft
> 关联: DESIGN_PERSPECTIVE_PLANNER.md, DESIGN_SEMANTIC_WORLD_MODEL.md

## 一、核心命题

### 1.1 旧假设 vs 新假设

```
旧假设: 图上的 Node = 世界里的 Object
  → ConceptNode(name, summary, edges)  — 标签 + 文本容器
  → SemanticObject = 包装层 (GraphNode++)  — 数据和行为混在一起

新假设: SemanticObject 是纯数据对象。ObjectRuntime 负责行为。
  → SemanticObject = identity + composition + projections + relations  — 纯数据
  → ObjectRuntime.render(object, perspective, lod) → Context  — 渲染管线
  → 数据和行为分离
```

### 1.2 三段设计的关系

```
DESIGN_PERSPECTIVE_PLANNER.md  → 怎么看（视角决策）           — 决策层
DESIGN_SEMANTIC_OBJECT.md      → 世界的基本单位是什么（对象模型）— 数据层
DESIGN_SEMANTIC_WORLD_MODEL.md → 世界是什么（全局模型）       — 全局层
```

### 1.3 对象操作系统

```
Graph 时代（旧）:           Object Runtime（新）:
  A → BFS → Node              Runtime → Perspective → LOD → ProjectionResolver → ContentProvider → Context
                                ↑           ↑        ↑            ↑                  ↑
                              决策        深度    多世界视图      统一数据源

这不是 RAG 改进。这是对象运行时。
SemanticObject 是数据，ObjectRuntime 负责把它渲染成 Context。
```

## 二、SemanticObject（纯数据）

### 2.1 定义

```python
@dataclass
class SemanticObject:
    """v4 的一等公民——纯数据对象。

    - 不包含任何渲染逻辑
    - 不直接访问任何存储
    - 所有行为由 ObjectRuntime 负责
    """
    identity: str                          # 唯一标识
    name: str                              # 显示名（如 "Runtime"）

    # 组合关系（带类型的纵向边）
    composition_edges: List[CompositionEdge]
    # [{target: "Observation", type: "contains"}, ...]
    # 类型: contains | pipeline | phase | owns | implements | strategy | refines

    # 投影（存的是 Resolver 引用——不是 Content）
    projection_resolvers: Dict[str, str]
    # "design" → "DesignResolver"
    # "code"   → "CodeResolver"
    # 值只是 resolver 的注册名，不持有实例

    # 层级坐标
    semantic_path: List[str]               # ["DialogMesh", "Runtime"]

    # 同级关系
    relations: List[Relation]              # depends_on, calls, implements...


@dataclass
class CompositionEdge:
    target: str          # 子对象 identity
    type: str            # "contains" | "pipeline" | "phase" | "owns" | "implements" | "strategy" | "refines"
    weight: float = 1.0


@dataclass
class LOD:
    """连续细节层次。"""
    level: float          # 1.0→4.0
    token_budget: int
    strategy: str

    @classmethod
    def from_horizon(cls, horizon: Horizon) -> "LOD":
        return cls(level=horizon.depth, token_budget=horizon.budget,
                   strategy=horizon.strategy)
```

### 2.2 和旧 ConceptGraph 的映射

| 旧 | 新 | 变化 |
|------|------|------|
| `graph.nodes[name]` | `SemanticObject` | dict→dataclass，纯数据 |
| `relations[type=contains]` | `composition_edges` | 独立字段，类型化 |
| `relations[type!=contains]` | `relations` | 保持不变 |
| `heading_path` | `semantic_path` | 物理→语义坐标 |
| `(无)` | `projection_resolvers` | 存 Resolver 注册名 |
| `(无)` | `(ObjectRuntime.render)` | 渲染逻辑外移 |

## 三、Projection Resolver（分离式投影）

### 3.1 三要素

```
1. ProjectionResolver 是注册式解析器 —— 不是存内容，是在注册中心注册的函数
2. ContentProvider 隔离存储 —— Resolver 不知道 Pool/CodeGraph/KnowledgeSpace
3. resolve(view) 接受 view 参数 —— 同一个对象可反回 summary/detail/history 不同视图
```

### 3.2 接口

```python
class ProjectionResolver(ABC):
    """投影解析器——同一个世界在不同视角下的内容生成策略。

    不持有存储引用。通过 ContentProvider 获取数据。
    不缓存内容。每次 resolve 动态生成。
    """
    name: str  # 注册名，如 "DesignResolver"

    @abstractmethod
    def resolve(self, target: SemanticObject, view: str,
                provider: "ContentProvider") -> str:
        """根据目标对象和视图类型，动态生成投影内容。

        view: "summary" | "definition" | "detail" | "history" | "full"
        """
        ...


class DesignResolver(ProjectionResolver):
    name = "DesignResolver"

    def resolve(self, target, view, provider):
        path = target.semantic_path
        if view == "summary":
            return provider.query_design(path, limit=1, max_chars=150)
        elif view == "definition":
            return provider.query_design(path, pattern="definition", limit=1)
        elif view == "history":
            return provider.query_design(path, pattern="evolution", limit=3)
        else:
            return provider.query_design(path, limit=5, max_chars=1000)


class CodeResolver(ProjectionResolver):
    name = "CodeResolver"
    world = "code"
    # 预留：通过 provider.code_lookup(target.name) 获取代码投影


class KnowledgeResolver(ProjectionResolver):
    name = "KnowledgeResolver"
    world = "knowledge"
    # 预留：通过 provider.knowledge_lookup(target.name) 获取冻结事实


class ConversationResolver(ProjectionResolver):
    name = "ConversationResolver"
    world = "conversation"
    # 预留：通过 provider.conversation_lookup(target.name) 获取话题片段


class SkillResolver(ProjectionResolver):
    name = "SkillResolver"
    world = "skill"
    # 预留：通过 provider.skill_lookup(target.name) 获取能力
```

### 3.3 ContentProvider —— 存储隔离

```python
class ContentProvider:
    """统一内容源——隔离 SemanticObject 和所有存储层。

    SemanticObject 不直接知道 ObservationPool/ConceptGraph/CodeStore。
    只有 ContentProvider 知道数据从哪来。
    """

    def __init__(self, observation_pool=None, semantic_index=None,
                 code_adapter=None, knowledge_space=None, skill_layer=None):
        self._pool = observation_pool
        self._semantic = semantic_index
        self._code = code_adapter
        self._knowledge = knowledge_space
        self._skill = skill_layer

    def query_design(self, path: List[str], pattern: str = None,
                     limit: int = 3, max_chars: int = 500) -> str:
        """从 ObservationPool 按 heading_path + pattern 查询设计内容。"""
        # 实现: 遍历 pool → 匹配 heading_path → 按 pattern 过滤 → 返回文本

    def code_lookup(self, name: str) -> str:
        """从代码仓库查询代码投影（预留）。"""

    def knowledge_lookup(self, name: str) -> str:
        """从 KnowledgeSpace 查询事实（预留）。"""

    def conversation_lookup(self, name: str) -> str:
        """从 ConversationTracker 查询话题（预留）。"""

    def skill_lookup(self, name: str) -> str:
        """从 SkillLayer 查询能力（预留）。"""
```

### 3.4 ResolverRegistry

```python
class ResolverRegistry:
    """投影解析器的注册中心。"""

    _registry: Dict[str, ProjectionResolver] = {
        "DesignResolver": DesignResolver(),
        "CodeResolver": CodeResolver(),
        "KnowledgeResolver": KnowledgeResolver(),
        "ConversationResolver": ConversationResolver(),
        "SkillResolver": SkillResolver(),
    }

    @classmethod
    def get(cls, name: str) -> Optional[ProjectionResolver]:
        return cls._registry.get(name)
```

### 3.5 Skill 的宿主

```
SemanticObject("Runtime")
  projection_resolvers["skill"] = "SkillResolver"

ObjectRuntime.render(obj, perspective, LOD) →
  → SkillResolver.resolve(obj, "summary", provider)
  → provider.skill_lookup("Runtime")
  → [RuntimeInitSkill, RuntimeHealthCheck, ...]

Skill 不再悬空——挂在对象的 skill_projection 上。
```

## 四、ObjectRuntime（行为层）

### 4.1 定位

```
SemanticObject = 纯数据（identity + composition + projections + relations）
ObjectRuntime  = 纯行为（render / zoom / navigate）

数据和行为分离，符合整个 v4 的设计风格。
render() 不是 SemanticObject 的方法——它是 ObjectRuntime 的行为。
```

### 4.2 接口

```python
class ObjectRuntime:
    """对象运行时——SemanticObject 的行为层。

    接受 Perspective + LOD + ContentProvider，将对象渲染为 Context。
    LOD 控制展开深度，Perspective 控制展开什么。
    """

    def __init__(self, registry: ResolverRegistry, provider: ContentProvider):
        self._registry = registry
        self._provider = provider
        self._current: Optional[SemanticObject] = None  # 当前观察位置

    def render(self, obj: SemanticObject, lod: LOD,
               perspective: Perspective) -> dict:
        """根据 Perspective 和 LOD 渲染对象视图。

        perspective.strategy → 决定激活哪些 projection
        lod.level             → 决定展开 composition 多深
        """
        result = {"name": obj.name, "lod": lod.level}

        # 1. 激活 projection: 根据 perspective 决定 view 和 projection 优先级
        view = self._view_for(perspective)
        proj_priority = self._projection_priority(perspective)

        # 2. 渲染投影内容
        for proj_name in proj_priority:
            resolver_name = obj.projection_resolvers.get(proj_name)
            if not resolver_name:
                continue
            resolver = self._registry.get(resolver_name)
            if resolver:
                content = resolver.resolve(obj, view, self._provider)
                if content:
                    result[proj_name] = content[:500]

        # 3. 按 LOD 展开 composition
        if lod.level >= 2.0:
            depth = int(lod.level) - 1
            result["composition"] = self._expand_composition(
                obj, depth, lod, perspective)

        # 4. LOD >= 3.0 时展开 relations
        if lod.level >= 3.0:
            result["relations"] = obj.relations[:10]

        return result

    def zoom(self, obj: SemanticObject, lod: LOD,
             perspective: Perspective) -> dict:
        """重新定位于对象并渲染。"""
        self._current = obj
        return self.render(obj, lod, perspective)

    def navigate(self, concept: str) -> Optional[SemanticObject]:
        """在当前对象的 composition 中定位子对象。"""
        for e in self._current.composition_edges:
            if e.target == concept:
                return self._lookup(e.target)
        return None

    def _view_for(self, perspective: Perspective) -> str:
        """Perspective → view 映射。"""
        return {
            "architecture": "definition",
            "execution": "detail",
            "engineering": "full",
            "evolution": "history",
        }.get(perspective.strategy, "summary")

    def _projection_priority(self, perspective: Perspective) -> List[str]:
        """Perspective → 投影优先级。"""
        return {
            "architecture": ["design"],
            "execution": ["knowledge", "design"],
            "engineering": ["code", "design"],
            "evolution": ["design", "knowledge"],
        }.get(perspective.strategy, ["design"])

    def _expand_composition(self, obj: SemanticObject, depth: int,
                            lod: LOD, perspective: Perspective) -> List[dict]:
        """按 depth 递归展开 composition_edges。"""
        if depth <= 0:
            return []
        result = []
        for edge in obj.composition_edges:
            child = self._lookup(edge.target)
            if child:
                entry = {"name": child.name, "type": edge.type}
                if depth > 1:
                    entry["children"] = self._expand_composition(
                        child, depth - 1, lod, perspective)
                # 每个子对象也渲染其投影
                view = self._view_for(perspective)
                entry["summary"] = self._render_summary(child, view)
                result.append(entry)
        return result

    def _render_summary(self, obj: SemanticObject, view: str) -> str:
        """渲染对象的一句话摘要。"""
        for resolver_name in obj.projection_resolvers.values():
            resolver = self._registry.get(resolver_name)
            if resolver:
                content = resolver.resolve(obj, view, self._provider)
                if content:
                    return content[:200]
        return obj.name

    def _lookup(self, identity: str) -> Optional[SemanticObject]:
        """通过 identity 查找对象（由外部注入 object_store）。"""
        if hasattr(self, '_object_store'):
            return self._object_store.get(identity)
        return None
```

## 五、数据流

```
用户: "Runtime 是怎么工作的？"

1. PerspectivePlanner.plan(text, budget=2000)
   → strategy="execution", horizon=Horizon(depth=3)
   → LOD = LOD.from_horizon(horizon) = LOD(level=3.0)

2. SemanticObject.locate("Runtime")
   → obj: SemanticObject(name="Runtime",
        composition_edges=[{target: "Observation", type: "contains"}, ...],
        projection_resolvers={"design": "DesignResolver", "knowledge": "KnowledgeResolver"},
        semantic_path=["DialogMesh", "Runtime"])

3. ObjectRuntime.render(obj, LOD(3.0), perspective)
   → view = "detail"（来自 execution strategy）
   → proj_priority = ["knowledge", "design"]
   → DesignResolver.resolve(obj, "detail", provider)
       → provider.query_design(["DialogMesh","Runtime"], pattern="definition")
       → "Runtime 是 v4 的核心执行引擎，负责四路径调度..."
   → KnowledgeResolver.resolve(obj, "detail", provider)
       → provider.knowledge_lookup("Runtime")
       → "Observation 依赖 RawEvent→Normalizer→ObservationBundle"

   → expand_composition(obj, depth=2)
       → Observation: type=contains, summary="ObservationCompiler 将..."
         → Normalizer: type=pipeline, summary="Clean→Canonicalize→Validate"
         → Projector: type=pipeline
       → Hypothesis: type=contains
       → Knowledge: type=contains

4. Context IR → 带层级 + 分投影的结构化上下文
```

## 六、Phase A 实现路线

### 不变的原则

- 不改现有管线（engine/assembler/sources 全部不动）
- 不复制数据（SemanticObject 是 graph node 的引用包装）
- 不破坏 ConceptGraph/SemanticIndex（它们继续作为存储层存在）

### 文件结构

```
core/agent/v4/compiler/
├── semantic_object.py      # SemanticObject + LOD (纯数据)
├── object_runtime.py       # ObjectRuntime (纯行为)
├── projection_resolver.py  # Resolver 接口 + DesignResolver + ResolverRegistry
├── content_provider.py     # ContentProvider (存储隔离)
└── ... (existing files)
```

### Step 1: 数据模型（semantic_object.py + lOD，~100行）

```python
@dataclass
class SemanticObject:       # identity, name, composition_edges, projection_resolvers, semantic_path, relations
@dataclass  
class CompositionEdge:      # target, type, weight
@dataclass
class LOD:                  # level, token_budget, strategy + from_horizon()
```

### Step 2: ContentProvider（content_provider.py，~80行）

```python
class ContentProvider:
    # query_design(path, pattern, limit, max_chars)
    # 从 ObservationPool + SemanticIndex 查内容
    # 其他方法预留（code_lookup 等返回空字符串）
```

### Step 3: ProjectionResolver（projection_resolver.py，~100行）

```python
DesignResolver.resolve(target, view, provider)  # 唯一完整实现
CodeResolver / KnowledgeResolver / ConversationResolver / SkillResolver  # 预留 stub
ResolverRegistry  # 注册中心
```

### Step 4: ObjectRuntime（object_runtime.py，~100行）

```python
ObjectRuntime.render(obj, lod, perspective)      # 渲染管线
ObjectRuntime.zoom(obj, lod, perspective)         # 定位渲染
ObjectRuntime._expand_composition(obj, depth)     # 递归展开
```

### Step 5: 工厂方法（~50行）

```python
def build_from_graph(graph: ConceptGraph, semantic: SemanticIndex,
                     pool) -> Dict[str, SemanticObject]:
    """从已有 ConceptGraph + SemanticIndex 构建 SemanticObject 字典。"""
```

### 验证

```python
obj = objects["Runtime"]
assert obj.name == "Runtime"
assert obj.semantic_path == ["DialogMesh", "Runtime"]
assert len(obj.composition_edges) >= 2  # Observation, Hypothesis, Knowledge...

runtime = ObjectRuntime(registry, provider)
result = runtime.render(obj, LOD(level=2.0), perspective)
assert "composition" in result
assert "design" in result  # DesignResolver 返回了定义
```
