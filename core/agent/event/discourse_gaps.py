"""Discourse gaps: backtracking + format adaptation.

Two missing features from full design:
1. Topic backtracking: "回到刚才的话题" → jump to previous block
2. Format router: XML (structured) / JSON (relational) / NL (fuzzy) based on content type"""
import json, re, logging
from typing import Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Topic Backtracker
# ═══════════════════════════════════════════════════════════

BACKTRACK_PATTERNS = [
    (r"回到(刚才|之前|上一个?)话?题", "recent"),
    (r"继续说(刚才|之前|上一个?)(的)?", "recent"),
    (r"回到.*?([^\s]{2,8})", "named"),  # 回到"JWT"的话题
    (r"刚才说的(.*?)(话题|问题|方案|设计)", "named"),
    (r"不对.*?不是.*?(回到|重新|重来)", "correction"),
]


@dataclass
class BacktrackResult:
    found: bool = False
    block_id: Optional[str] = None
    block_text: Optional[str] = None
    reason: str = ""


class TopicBacktracker:
    """Detect user intent to backtrack and return the target block."""

    def detect(self, text: str, session_id: str, engine) -> BacktrackResult:
        for pattern, kind in BACKTRACK_PATTERNS:
            match = re.search(pattern, text)
            if match:
                blocks = self._get_recent_blocks(session_id, engine)

                if kind == "recent" and len(blocks) >= 2:
                    prev = blocks[-2]  # previous block
                    return BacktrackResult(True, prev.get("id"),
                                           prev.get("text", "")[:200], "recent")

                if kind == "named":
                    name = match.group(1) if match.lastindex else match.group(0)
                    # Search blocks by entity name
                    dt = getattr(engine, '_discourse_tree', None)
                    if dt and hasattr(dt, 'find_block_by_reference'):
                        bid = dt.find_block_by_reference(session_id, name)
                        if bid:
                            return BacktrackResult(True, bid, f"named:{name}", "named")

                if kind == "correction":
                    return BacktrackResult(True, None, None, "correction_requested")

        return BacktrackResult()

    def _get_recent_blocks(self, session_id: str, engine) -> list:
        dt = getattr(engine, '_discourse_tree', None)
        if dt and hasattr(dt, 'get_block_relations'):
            rel = dt.get_block_relations(session_id)
            blocks = list(rel.get("blocks", {}).items())
            # Sort by depth/creation order
            return [{"id": bid, "text": info.get("summary", "")} for bid, info in blocks[-5:]]
        return []


# ═══════════════════════════════════════════════════════════
#  Format Router
# ═══════════════════════════════════════════════════════════

@dataclass
class FormatDecision:
    format: str  # "xml" | "json" | "markdown" | "mixed"
    confidence: float
    reasoning: str


class FormatRouter:
    """Route content to appropriate output format based on structure.

    Rules:
      XML:    complex hierarchical structures (configs, schemas, tree data)
      JSON:   relational/key-value data (APIs, entities, metrics)
      Markdown: natural language, explanations, prose
      Mixed:  both structured + unstructured content"""

    def decide(self, text: str, context: dict = None) -> FormatDecision:
        scores = {"xml": 0.0, "json": 0.0, "markdown": 0.0}

        # Hierarchical signals → XML
        if re.search(r"(层级|树|嵌套|递归|schema|xsd|DTD|父子|祖孙)", text):
            scores["xml"] += 0.3
        if re.search(r"(<[a-zA-Z]+>|<[a-zA-Z]+ |</)", text):
            scores["xml"] += 0.4
        if re.search(r"(配置|接口定义|协议|spec|contract)", text):
            scores["xml"] += 0.2

        # Relational signals → JSON
        if re.search(r"(\{.*\}|\[\s*\{)", text):
            scores["json"] += 0.4
        if re.search(r"(API|接口|JSON|json|键值|key.value|字段|属性|列)", text):
            scores["json"] += 0.3
        if re.search(r"(数据|表|记录|条目|列表|数组)", text):
            scores["json"] += 0.2

        # Natural language → Markdown
        if re.search(r"(解释|说明|描述|介绍|什么是|如何|为什么|怎么样)", text):
            scores["markdown"] += 0.3
        if re.search(r"(方案|建议|分析|评估|考虑|认为|觉得)", text):
            scores["markdown"] += 0.2
        # Default bias: most content is natural language
        scores["markdown"] += 0.1

        best = max(scores, key=scores.get)
        return FormatDecision(best, scores[best], f"scores: {scores}")

    def format_output(self, content: str, decision: FormatDecision) -> str:
        """Apply formatting based on decision."""
        if decision.format == "xml":
            return self._wrap_xml(content)
        elif decision.format == "json":
            return self._wrap_json(content)
        return content  # markdown: as-is

    def _wrap_xml(self, content: str) -> str:
        """Wrap content in XML structure."""
        # Try to detect if already XML
        if content.strip().startswith("<"):
            return content
        lines = content.strip().split("\n")
        parts = []
        current_section = None
        for line in lines:
            if re.match(r"^[#]{1,3}\s", line):  # Markdown heading → XML section
                current_section = re.sub(r"^#+\s+", "", line).strip()
                continue
            if current_section:
                parts.append(f"  <{current_section}>{line.strip()}</{current_section}>")
            else:
                parts.append(f"  <item>{line.strip()}</item>")
        return f"<response>\n" + "\n".join(parts) + "\n</response>"

    def _wrap_json(self, content: str) -> str:
        """Try to structure as JSON."""
        if content.strip().startswith("{"):
            return content
        lines = [l.strip() for l in content.strip().split("\n") if l.strip()]
        items = []
        current_key = None
        for line in lines:
            if ":" in line and not line.startswith("-"):
                k, v = line.split(":", 1)
                items.append(f'  "{k.strip()}": "{v.strip()}"')
            else:
                items.append(f'  "item": "{line}"')
        return "{\n" + ",\n".join(items) + "\n}"
