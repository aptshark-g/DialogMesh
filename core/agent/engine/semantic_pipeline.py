"""SemanticObject pipeline — extraction → LLM classification → identity → storage.

Once an object enters the system, it stays. Every object has a permanent
identity trace: id, type, confidence, extracted_from, relations, versions.
"""
import json, os, time, uuid, hashlib
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "data")
OBJECTS_FILE = os.path.join(DATA_DIR, "world_objects.json")


@dataclass
class SemanticObject:
    """Permanent semantic object with full identity trace."""
    identity: str                              # unique id (sha256 digest)
    name: str                                  # display name
    obj_type: str                              # concept, entity, task, topic, tool, file
    confidence: float = 0.5                    # LLM confidence score
    extracted_from: str = ""                   # source text
    session_id: str = ""                       # which session created it
    description: str = ""                      # LLM-generated description
    relations: List[Dict] = field(default_factory=list)  # [{target, type}]
    aliases: List[str] = field(default_factory=list)     # alternative names
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 1
    llm_validated: bool = False


# ═══════════════════════════════════════════════════════════
#  Pipeline
# ═══════════════════════════════════════════════════════════

class SemanticObjectPipeline:
    """Extract + classify + dedup + store semantic objects from conversation text."""

    def __init__(self, llm_provider=None):
        self._objects: Dict[str, SemanticObject] = {}
        self._llm = llm_provider
        self._load()

    def _load(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(OBJECTS_FILE):
            try:
                data = json.load(open(OBJECTS_FILE, encoding="utf-8"))
                for obj_id, obj_data in data.items():
                    self._objects[obj_id] = SemanticObject(**obj_data)
            except Exception:
                pass

    def _save(self):
        with open(OBJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump({k: asdict(v) for k, v in self._objects.items()},
                      f, indent=2, ensure_ascii=False, default=str)

    def extract_from_text(self, text: str, session_id: str = "") -> List[SemanticObject]:
        """Extract entities from text using syntactic decomposition + LLM classification."""
        results = []

        # Layer 1: syntactic extraction via SyntacticDecomposer
        try:
            from core.agent.compiler.discourse_block_tree import SyntacticDecomposer
            decomposer = SyntacticDecomposer()
            edus = decomposer.decompose(text)
            entities = set()
            for edu in edus:
                for e in getattr(edu, 'entities', []):
                    name = e.name if hasattr(e, 'name') else str(e)
                    if len(name) > 1:
                        entities.add(name)
        except Exception:
            entities = set()
            # Fallback: simple keyword extraction
            words = text.replace("，", " ").replace("。", " ").split()
            entities = {w for w in words if len(w) >= 2 and not w.isascii()}

        # Layer 2: LLM classification (if available)
        for entity in list(entities)[:10]:
            obj_type, confidence, desc = self._classify(entity, text)
            identity = self._make_identity(entity, obj_type)
            if identity in self._objects:
                obj = self._objects[identity]
                obj.aliases.append(entity) if entity not in obj.aliases else None
                obj.updated_at = time.time()
            else:
                obj = SemanticObject(
                    identity=identity, name=entity, obj_type=obj_type,
                    confidence=confidence, description=desc or f"从对话中提取: {text[:60]}",
                    extracted_from=text[:200], session_id=session_id,
                    llm_validated=self._llm is not None,
                )
                self._objects[identity] = obj
            results.append(obj)

        if results:
            self._save()
        return results

    def _classify(self, entity: str, context: str) -> tuple:
        """Classify entity type using LLM or fallback heuristics."""
        if self._llm:
            try:
                prompt = f"""将以下实体分类为: concept(概念)/entity(实体)/task(任务)/topic(主题)/tool(工具)/file(文件)

实体: "{entity}"
上下文: "{context[:200]}"

返回JSON: {{"type":"...","confidence":0.0-1.0,"description":"一句话描述"}}"""
                result = self._llm.generate(prompt)
                if result:
                    import re
                    match = re.search(r'\{[^}]+\}', result)
                    if match:
                        d = json.loads(match.group())
                        return d.get("type", "concept"), d.get("confidence", 0.5), d.get("description", "")
            except Exception:
                pass

        # Fallback: heuristic classification
        if any(kw in entity for kw in ["系统", "框架", "架构", "设计"]):
            return "concept", 0.6, f"概念: {entity}"
        elif any(kw in entity for kw in ["文件", "目录", "路径", ".py", ".js"]):
            return "file", 0.8, f"文件: {entity}"
        elif any(kw in entity for kw in ["任务", "完成", "实现", "开发"]):
            return "task", 0.5, f"任务: {entity}"
        elif any(kw in context.lower() for kw in ["topic", "主题", "话题"]):
            return "topic", 0.4, f"话题: {entity}"
        return "entity", 0.3, f"实体: {entity}"

    def _make_identity(self, name: str, obj_type: str) -> str:
        digest = hashlib.sha256(f"{name}:{obj_type}".encode()).hexdigest()[:12]
        return f"obj_{digest}"

    def get_all(self) -> List[Dict]:
        return [asdict(o) for o in self._objects.values()]

    def search(self, keyword: str) -> List[Dict]:
        kw = keyword.lower()
        return [asdict(o) for o in self._objects.values()
                if kw in o.name.lower() or any(kw in a.lower() for a in o.aliases)]

    def add_object(self, name: str, obj_type: str = "concept",
                   description: str = "") -> SemanticObject:
        identity = self._make_identity(name, obj_type)
        if identity in self._objects:
            return self._objects[identity]
        obj = SemanticObject(
            identity=identity, name=name, obj_type=obj_type,
            description=description or f"手动添加", confidence=1.0,
            llm_validated=False,
        )
        self._objects[identity] = obj
        self._save()
        return obj

    def add_relation(self, source: str, target: str, rel_type: str = "related"):
        if source in self._objects and target in self._objects:
            self._objects[source].relations.append({"target": target, "type": rel_type})
            self._save()

    def remove_object(self, identity: str):
        if identity in self._objects:
            del self._objects[identity]
            self._save()

    def to_graph(self) -> dict:
        """Export as graph nodes + edges for visualization."""
        nodes = [{"id": o.identity, "label": o.name, "type": o.obj_type,
                   "confidence": o.confidence, "description": o.description[:80]}
                 for o in self._objects.values()]
        edges = []
        for o in self._objects.values():
            for r in o.relations:
                edges.append({"source": o.identity, "target": r["target"],
                              "type": r["type"]})
        return {"nodes": nodes, "edges": edges}
