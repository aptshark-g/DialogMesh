# -*- coding: utf-8 -*-
"""LLMDAGBuilder — LLM-driven DAG construction via diverge→learn→converge.

§十二 三层范式映射:
  diverge  = 发散阶段 (T=0.8, 无上下文约束)
  learn    = 学习阶段 (arXiv/EventLog/参考文档)
  converge = 收束阶段 (T=0.1, 完整上下文 + 约束过滤)

BlueprintEngine orchestrates by strategy:
  TEMPLATE → direct return
  HYBRID   → template + LLM override
  LLM_DRIVEN → diverge → learn → converge
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
import re
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

from core.agent.blueprint.models import BlueprintDAG, BlueprintNode, BlueprintEdge

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════

SWITCH_URL = "http://127.0.0.1:8080"
SWITCH_KEY = "dm-client"
DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL = "deepseek-v4-flash"

DIVERGE_SYSTEM = """你是 DialogMesh 的图构建发散器。根据用户输入，生成多种可能的执行路径。

每条路径是一个节点序列，节点类型只能是: pcr, intent, context, subgraph, profile, llm_reply, behavior, meta。

输出严格 JSON:
```json
[
  {
    "path": [
      {"chain": "pcr", "reason": "先分析路由"},
      {"chain": "intent", "reason": "再拆分意图"},
      {"chain": "profile", "reason": "加载画像"},
      {"chain": "llm_reply", "reason": "最终回复"}
    ],
    "confidence": 0.9,
    "rationale": "标准对话流程"
  }
]
```

规则:
- 每条路径 2-6 个节点
- 必须包含 pcr 作为起点, llm_reply 作为终点
- 给出每条路径的推导原因
- 不要让之前的上下文约束你的思路
- 只输出 JSON，不要其他文字"""

CONVERGE_SYSTEM = """你是 DialogMesh 的图构建收束器。从多条候选路径中选择最优一条，输出完整的 BlueprintDAG。

输入包含: 用户原文、发散阶段的多条候选路径、学习阶段检索到的参考信息。

输出严格 JSON:
```json
{
  "nodes": [
    {"node_id": "pcr_0", "chain": "pcr", "priority": 0, "checkpoint": false, "params": {}},
    {"node_id": "intent_1", "chain": "intent", "priority": 0, "checkpoint": false, "params": {}},
    {"node_id": "llm_2", "chain": "llm_reply", "priority": 2, "checkpoint": false, "params": {}}
  ],
  "edges": [
    {"from_node": "pcr_0", "to_node": "intent_1", "data_key": "route"},
    {"from_node": "intent_1", "to_node": "llm_2", "data_key": "intent_context"}
  ],
  "confidence": 0.85,
  "design_rationale": "选择此路径的原因"
}
```

规则:
- node_id 格式: {chain}_{序号} (如 pcr_0, intent_1)
- edges 的 data_key: route, intent_context, assembled_context, compiled_subgraph, profile_text, compass
- 依赖必须正确: to_node 依赖的 data_key 必须由 from_node 产出
- confidence 0.0-1.0
- 节点 2-7 个
- 只输出 JSON，不要其他文字"""


@dataclass
class Hypothesis:
    """One candidate execution path from diverge phase."""
    nodes: List[Dict[str, str]]  # [{chain, reason}, ...]
    confidence: float
    rationale: str


@dataclass
class LearningResult:
    """Information gathered during learn phase."""
    arxiv_matches: List[Dict[str, str]] = field(default_factory=list)
    eventlog_matches: List[Dict[str, Any]] = field(default_factory=list)
    reference_matches: List[str] = field(default_factory=list)


class LLMDAGBuilder:
    """LLM-driven DAG construction: diverge → learn → converge."""

    def __init__(self, provider: str = DEFAULT_PROVIDER, model: str = DEFAULT_MODEL):
        self.provider = provider
        self.model = model

    # ─── Core LLM call ───

    def _call_llm(self, system_prompt: str, user_prompt: str, temperature: float = 0.5,
                  max_tokens: int = 2000) -> str:
        """Call switch gateway LLM. Returns response text or empty string on failure."""
        body = {
            "provider": self.provider,
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            data = json.dumps(body).encode()
            req = urllib.request.Request(
                f"{SWITCH_URL}/v1/chat/completions",
                data=data,
                headers={"Authorization": f"Bearer {SWITCH_KEY}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
            return result.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.warning("LLM call failed: %s", e)
            return ""

    def _extract_json(self, text: str) -> Optional[Any]:
        """Extract JSON from LLM output (may have markdown fences)."""
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search(r'\{[\s\S]*\}|\[[\s\S]*\]', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    # ─── Phase 1: Diverge (发散) ───

    def diverge(self, text: str, intent: str) -> List[Hypothesis]:
        """LLM T=0.8, no context constraint — generate multiple candidate paths.

        Returns list of Hypothesis objects. Falls back to empty list on failure.
        """
        prompt = f"用户意图: {intent}\n用户输入: {text[:1000]}\n\n请生成 2-4 种可能的执行路径。"
        response = self._call_llm(DIVERGE_SYSTEM, prompt, temperature=0.8, max_tokens=1500)
        if not response:
            logger.warning("Diverge LLM returned empty — falling back")
            return []

        data = self._extract_json(response)
        if not isinstance(data, list):
            logger.warning("Diverge: unexpected format: %s", str(data)[:200])
            return []

        hypotheses = []
        for item in data:
            if not isinstance(item, dict):
                continue
            path = item.get("path", [])
            if not path:
                continue
            hypotheses.append(Hypothesis(
                nodes=path,
                confidence=float(item.get("confidence", 0.5)),
                rationale=item.get("rationale", ""),
            ))
        logger.info("Diverge: generated %d hypotheses (intent=%s)", len(hypotheses), intent)
        return hypotheses

    # ─── Phase 2: Learn (学习) ───

    def learn(self, hypotheses: List[Hypothesis], intent: str,
              eventlog_query: Optional[str] = None) -> LearningResult:
        """Gather external information — arXiv API + local refs.

        Queries arXiv for papers matching the intent + chain keywords.
        Falls back to local reference map if arxiv is unreachable.
        """
        result = LearningResult()
        if not hypotheses:
            return result

        # Collect chain names mentioned in hypotheses
        chains_mentioned = set()
        for h in hypotheses:
            for n in h.nodes:
                chains_mentioned.add(n.get("chain", ""))

        # 1. arXiv search (non-blocking, quick timeout)
        try:
            import urllib.request, urllib.parse
            query = urllib.parse.quote(f"{intent} agent orchestration")
            url = f"http://export.arxiv.org/api/query?search_query=all:{query}&max_results=3&sortBy=relevance"
            req = urllib.request.Request(url, headers={"User-Agent": "DialogMesh/6.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode()
            # Parse arxiv XML for titles
            import re as _re
            for m in _re.finditer(r'<title>(.*?)</title>', body):
                title = m.group(1).strip()
                if title and "Query" not in title:
                    result.arxiv_matches.append({"title": title, "source": "arxiv"})
        except Exception:
            pass  # arxiv unreachable — continue with local refs

        # 2. Local reference map (always available)
        reference_map = {
            "代码分析": ["TEMPLATE: code_analysis (5节点: pcr→intent→context→subgraph→llm_reply)"],
            "通用对话": ["TEMPLATE: general_chat (4节点: pcr→intent→profile→llm_reply)"],
            "任务规划": ["TEMPLATE: task_planning (6节点: pcr→intent→context→subgraph→profile→llm_reply)"],
            "数据搜索": ["TEMPLATE: data_search (3节点: pcr→intent→llm_reply)"],
            "因果推理": ["STRATEGY: LLM_DRIVEN — LLM 全权构建完整DAG, PlanGate checkpoint 必须审核"],
        }
        for known, lines in reference_map.items():
            if known in intent or intent in known:
                result.reference_matches = lines
                break

        logger.info("Learn: %d arxiv hits, %d ref matches, %d chains (intent=%s)",
                     len(result.arxiv_matches), len(result.reference_matches),
                     len(chains_mentioned), intent)
        return result

    # ─── Phase 3: Converge (收束) ───

    def converge(self, text: str, intent: str, hypotheses: List[Hypothesis],
                 learning: LearningResult) -> Optional[BlueprintDAG]:
        """LLM T=0.1, full context — filter + merge hypotheses into final BlueprintDAG.

        Returns BlueprintDAG or None on failure (caller falls back to TEMPLATE).
        """
        # Build context
        hypotheses_text = ""
        for i, h in enumerate(hypotheses):
            nodes_text = " → ".join(f"{n.get('chain','?')}({n.get('reason','?')})" for n in h.nodes)
            hypotheses_text += f"路径{i+1} (c={h.confidence:.2f}): {nodes_text}\n  理由: {h.rationale}\n"

        learning_text = "\n".join(learning.reference_matches) if learning.reference_matches else "无"

        prompt = (
            f"用户意图: {intent}\n"
            f"用户输入: {text[:1000]}\n\n"
            f"候选路径:\n{hypotheses_text}\n"
            f"参考信息:\n{learning_text}\n\n"
            f"请选择最优路径并输出完整的 BlueprintDAG JSON。"
        )

        response = self._call_llm(CONVERGE_SYSTEM, prompt, temperature=0.1, max_tokens=2000)
        if not response:
            logger.warning("Converge LLM returned empty — falling back")
            return None

        data = self._extract_json(response)
        if not isinstance(data, dict):
            logger.warning("Converge: unexpected format: %s", str(data)[:200])
            return None

        # Parse nodes
        nodes = []
        for n in data.get("nodes", []):
            try:
                nodes.append(BlueprintNode(
                    node_id=n.get("node_id", "?"),
                    chain=n.get("chain", "intent"),
                    params=n.get("params", {}),
                    priority=int(n.get("priority", 0)),
                    checkpoint=bool(n.get("checkpoint", False)),
                ))
            except (ValueError, KeyError) as e:
                logger.warning("Invalid node in converge output: %s", e)

        # Parse edges
        edges = []
        for e in data.get("edges", []):
            edges.append(BlueprintEdge(
                from_node=e.get("from_node", "?"),
                to_node=e.get("to_node", "?"),
                data_key=e.get("data_key", "data"),
                required=bool(e.get("required", True)),
            ))

        confidence = float(data.get("confidence", 0.5))
        rationale = data.get("design_rationale", "")

        dag = BlueprintDAG(
            nodes=nodes,
            edges=edges,
            strategy="LLM_DRIVEN",
            confidence=confidence,
            design_rationale=rationale,
        )

        errors = dag.validate()
        if errors:
            logger.warning("Converge produced invalid DAG: %s", errors)

        logger.info("Converge: built DAG with %d nodes, %d edges (c=%.2f)",
                     dag.node_count, len(dag.edges), confidence)
        return dag

    # ─── Convenience: full LLM_DRIVEN pipeline ───

    def build_llm_driven(self, text: str, intent: str) -> Optional[BlueprintDAG]:
        """Full diverge → learn → converge pipeline."""
        hypotheses = self.diverge(text, intent)
        if not hypotheses:
            return None
        learning = self.learn(hypotheses, intent)
        return self.converge(text, intent, hypotheses, learning)
