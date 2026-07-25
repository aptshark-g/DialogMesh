"""Blueprint System — ENGINEERING_PLANNING_SKILL §6-10 implementation.

Blueprint bundles: SkillRegistry → TaskDecomposer → AgentAllocator → DependencyResolver → Scheduler.
Default strategy: HYBRID (RULE_BASED template + LLM context-aware override).
5 strategies: RULE_BASED, TEMPLATE, HYBRID, LLM_DRIVEN, RECOVERY.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import logging
import time

logger = logging.getLogger(__name__)


class BlueprintStrategy(Enum):
    RULE_BASED = "rule_based"    # Pure rules, no LLM
    TEMPLATE = "template"        # Pre-defined task templates
    HYBRID = "hybrid"            # Template + LLM override (default)
    LLM_DRIVEN = "llm_driven"    # LLM decides everything
    RECOVERY = "recovery"        # Retry after failure, extra checks


# ═══ Data Models ═══

@dataclass
class SkillDef:
    """Registered skill — maps intent patterns to action templates."""
    skill_id: str
    name: str
    description: str
    intent_keywords: List[str]  # e.g. ["analyze", "security", "vulnerability"]
    tools_needed: List[str]      # e.g. ["read", "grep", "edit"]
    template_steps: List[Dict]   # Pre-defined step templates
    constraints: List[str]       # e.g. ["no_system_files", "read_only"]
    confidence: float = 0.5
    usage_count: int = 0


@dataclass
class TaskStep:
    """One decomposed step in a plan."""
    index: int
    action: str
    tool: str
    params: Dict = field(default_factory=dict)
    depends_on: List[int] = field(default_factory=list)  # Step indices
    agent_id: Optional[str] = None
    skill_id: Optional[str] = None
    priority: int = 5
    estimated_cost_ms: int = 100


@dataclass
class Blueprint:
    """Complete blueprint — matched skill + decomposed steps + agent mapping."""
    blueprint_id: str
    strategy: BlueprintStrategy
    matched_skill: Optional[SkillDef] = None
    steps: List[TaskStep] = field(default_factory=list)
    agent_assignments: Dict[int, str] = field(default_factory=dict)
    dependency_graph: Dict[int, List[int]] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)


# ═══ SkillRegistry ═══

class SkillRegistry:
    """Register and match skills based on intent patterns."""

    def __init__(self):
        self._skills: Dict[str, SkillDef] = {}
        self._register_defaults()

    def _register_defaults(self):
        defaults = [
            SkillDef("code_analysis", "Code Analysis",
                     "Analyze code for bugs, security, style",
                     ["analyze", "security", "bug", "vulnerability", "review", "audit"],
                     ["read", "grep", "glob"],
                     [{"action": "Read target files", "tool": "read"},
                      {"action": "Search for patterns", "tool": "grep"},
                      {"action": "Generate report", "tool": "write"}],
                     ["no_system_files"]),
            SkillDef("code_fix", "Code Fix",
                     "Fix bugs and apply patches",
                     ["fix", "patch", "edit", "correct", "repair"],
                     ["read", "edit", "write"],
                     [{"action": "Read file", "tool": "read"},
                      {"action": "Apply fix", "tool": "edit"},
                      {"action": "Validate fix", "tool": "bash"}],
                     ["require_review"]),
            SkillDef("test_run", "Run Tests",
                     "Execute test suites",
                     ["test", "run", "execute", "check"],
                     ["bash"],
                     [{"action": "Run test command", "tool": "bash"},
                      {"action": "Report results", "tool": "write"}],
                     []),
            SkillDef("config_update", "Configuration Update",
                     "Update config files",
                     ["config", "configure", "setup", "setting"],
                     ["read", "edit"],
                     [{"action": "Read config", "tool": "read"},
                      {"action": "Update config", "tool": "edit"}],
                     ["require_review", "forbidden:/etc/"]),
            SkillDef("data_search", "Data Search",
                     "Search codebase for patterns",
                     ["search", "find", "grep", "where", "locate"],
                     ["grep", "glob", "read"],
                     [{"action": "Search patterns", "tool": "grep"},
                      {"action": "Read matches", "tool": "read"}],
                     ["read_only"]),
        ]
        for s in defaults:
            self.register(s)

    def register(self, skill: SkillDef):
        self._skills[skill.skill_id] = skill

    def match(self, intent: str, tools_available: List[str] = None,
              strategy: BlueprintStrategy = BlueprintStrategy.HYBRID) -> Optional[SkillDef]:
        """Match intent text to the best skill."""
        intent_lower = intent.lower()
        best_match = None
        best_score = 0

        for skill in self._skills.values():
            score = 0
            for kw in skill.intent_keywords:
                if kw in intent_lower:
                    score += 1
            # Usage bonus: frequently used skills get priority
            score += min(skill.usage_count * 0.1, 1.0)

            # Tool compatibility bonus
            if tools_available and skill.tools_needed:
                available = sum(1 for t in skill.tools_needed if t in tools_available)
                score += available / len(skill.tools_needed)

            if score > best_score:
                best_score = score
                best_match = skill

        if strategy == BlueprintStrategy.RULE_BASED and best_score < 1:
            return None
        if best_score >= 1:
            best_match.usage_count += 1
            return best_match
        return None


# ═══ TaskDecomposer ═══

class TaskDecomposer:
    """Decompose matched skill into concrete task steps."""

    def decompose(self, skill: SkillDef, intent: str, context: dict = None,
                  strategy: BlueprintStrategy = BlueprintStrategy.HYBRID) -> List[TaskStep]:
        """Convert skill template into executable steps."""
        steps = []
        for i, tmpl in enumerate(skill.template_steps):
            params = {}
            # Extract file paths from intent
            import re
            paths = re.findall(r'[\w./-]+\.(?:py|js|ts|yaml|json|md|toml|cfg|conf|ini)',
                               intent)
            if tmpl["tool"] in ("read", "edit", "write") and paths:
                params["path"] = paths[0] if i < len(paths) else paths[-1]
            if tmpl["tool"] in ("grep", "glob") and "file" in str(context or {}).lower():
                params["pattern"] = context.get("file_pattern", "*")

            step = TaskStep(
                index=i,
                action=tmpl["action"],
                tool=tmpl["tool"],
                params=params,
                depends_on=[i - 1] if i > 0 else [],
                skill_id=skill.skill_id,
                estimated_cost_ms=100,
            )
            steps.append(step)

        return steps


# ═══ AgentAllocator ═══

class AgentAllocator:
    """Assign task steps to agents (sub-agent or main)."""

    def allocate(self, steps: List[TaskStep], max_agents: int = 8) -> Dict[int, str]:
        """Map step indices to agent IDs."""
        assignments = {}
        agent_idx = 0

        for step in steps:
            if step.tool in ("bash", "edit"):
                # Heavy steps → separate sub-agent
                assignments[step.index] = f"agent_{agent_idx}"
                agent_idx = min(agent_idx + 1, max_agents - 1)
            else:
                assignments[step.index] = f"agent_{agent_idx}"

        return assignments


# ═══ DependencyResolver ═══

class DependencyResolver:
    """Resolve step dependencies into execution order."""

    def resolve(self, steps: List[TaskStep]) -> Dict[int, List[int]]:
        """Build dependency graph from step.depends_on."""
        graph = {}
        for step in steps:
            graph[step.index] = step.depends_on.copy()
        return graph

    def topological_order(self, graph: Dict[int, List[int]]) -> List[int]:
        """Topological sort — steps in execution order."""
        in_degree = {k: 0 for k in graph}
        for deps in graph.values():
            for d in deps:
                if d in in_degree:
                    in_degree[d] += 1

        queue = [k for k, v in in_degree.items() if v == 0]
        order = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for n, deps in graph.items():
                if node in deps:
                    in_degree[n] -= 1
                    if in_degree[n] == 0:
                        queue.append(n)

        return order if len(order) == len(graph) else list(range(len(graph)))


# ═══ BlueprintEngine ═══

class BlueprintEngine:
    """Unified Blueprint system — default HYBRID strategy."""

    def __init__(self, strategy: BlueprintStrategy = BlueprintStrategy.HYBRID,
                 llm=None, param_registry=None):
        self.strategy = strategy
        self.registry = SkillRegistry()
        self.decomposer = TaskDecomposer()
        self.allocator = AgentAllocator()
        self.resolver = DependencyResolver()
        self._llm = llm
        self._params = param_registry
        self._blueprint_count = 0

    def plan(self, intent: str, tools_available: List[str] = None,
             context: dict = None) -> Blueprint:
        """Create a Blueprint from user intent."""
        self._blueprint_count += 1

        # 1. Skill matching
        skill = self.registry.match(intent, tools_available, self.strategy)

        if not skill:
            # No skill matched — fallback to generic read-then-report
            skill = SkillDef("generic", "Generic Action", "Fallback plan",
                             ["help", "do", "run"],
                             tools_available or ["read", "write"],
                             [{"action": "Read context", "tool": "read"},
                              {"action": "Report result", "tool": "write"}],
                             [])
            self.registry.register(skill)

        # 2. Decompose into steps
        steps = self.decomposer.decompose(skill, intent, context, self.strategy)

        # 3. LLM override (HYBRID/LLM_DRIVEN)
        if self.strategy in (BlueprintStrategy.HYBRID, BlueprintStrategy.LLM_DRIVEN):
            steps = self._llm_override(steps, intent, context)

        # 4. Allocate to agents
        assignments = self.allocator.allocate(steps)

        # 5. Resolve dependencies
        dep_graph = self.resolver.resolve(steps)
        order = self.resolver.topological_order(dep_graph)

        return Blueprint(
            blueprint_id=f"bp_{self._blueprint_count}",
            strategy=self.strategy,
            matched_skill=skill,
            steps=steps,
            agent_assignments=assignments,
            dependency_graph=dep_graph,
            metadata={
                "intent": intent,
                "tools_available": tools_available,
                "step_order": order,
                "constraints": skill.constraints,
            },
        )

    def _llm_override(self, steps: List[TaskStep], intent: str,
                      context: dict = None) -> List[TaskStep]:
        """LLM can adjust steps: reorder, add, remove, modify."""
        if not self._llm:
            return steps
        if self.strategy == BlueprintStrategy.RULE_BASED:
            return steps

        # Build prompt
        step_desc = "\n".join(f"  {s.index}: [{s.tool}] {s.action}" for s in steps)
        prompt = (
            f"Intent: {intent[:200]}\n"
            f"Planned steps:\n{step_desc}\n\n"
            "Do the steps need adjustment? Reply JSON with optional changes:\n"
            '{"adjustments": [{"index": 0, "action": "new_tool_or_action"}], "add": []}'
        )

        try:
            response = self._llm.generate(prompt, max_tokens=100, temperature=0.1)
            # Parse LLM output
            import json
            if isinstance(response, str):
                data = json.loads(response)
            else:
                data = response
            adjustments = data.get("adjustments", [])
            for adj in adjustments:
                idx = adj.get("index", -1)
                if 0 <= idx < len(steps):
                    if "tool" in adj:
                        steps[idx].tool = adj["tool"]
                    if "action" in adj:
                        steps[idx].action = adj["action"]
        except Exception:
            pass  # LLM unavailable → use template as-is

        return steps
