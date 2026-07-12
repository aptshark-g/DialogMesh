"""Runtime Builder: programmatic DAG construction for v4 cognitive pipelines."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import yaml


@dataclass
class ModuleNode:
    """A node in the Runtime DAG."""
    name: str
    adapter: str
    module_class: str = ""
    timeout_ms: int = 5000
    retry: int = 1
    params: dict = field(default_factory=dict)
    trigger: str = ""
    trigger_config: dict = field(default_factory=dict)
    path: str = "async"


@dataclass
class DAGEdge:
    """A directed edge between two modules in the DAG."""
    from_module: str
    to_module: str


@dataclass
class RuntimeDAG:
    """A complete Runtime DAG that can be exported as YAML config."""
    name: str
    nodes: List[ModuleNode] = field(default_factory=list)
    edges: List[DAGEdge] = field(default_factory=list)

    def to_yaml(self) -> str:
        """Export the DAG as a runtime.yaml string."""
        paths: Dict[str, list] = {}
        for node in self.nodes:
            if node.path not in paths:
                paths[node.path] = []
            entry = {
                "name": node.name,
                "adapter": node.adapter,
                "timeout_ms": node.timeout_ms,
                "retry": node.retry,
                "params": node.params,
            }
            if node.trigger:
                entry["trigger"] = node.trigger
            if node.trigger_config:
                entry["trigger_config"] = node.trigger_config
            paths[node.path].append(entry)

        config = {
            "version": "1.0",
            "dag_name": self.name,
            "paths": paths,
            "edges": [
                {"from": e.from_module, "to": e.to_module} for e in self.edges
            ],
        }
        return yaml.dump(config, default_flow_style=False, allow_unicode=True)

    def save(self, path: str) -> None:
        """Save the DAG as a runtime YAML file."""
        import pathlib
        pathlib.Path(path).write_text(self.to_yaml(), encoding="utf-8")

    def validate(self) -> Tuple[bool, List[str]]:
        """Validate the DAG: check all edges reference existing nodes."""
        errors = []
        node_names = {n.name for n in self.nodes}
        for edge in self.edges:
            if edge.from_module not in node_names:
                errors.append(f"Edge from unknown module: {edge.from_module}")
            if edge.to_module not in node_names:
                errors.append(f"Edge to unknown module: {edge.to_module}")
        return len(errors) == 0, errors


class RuntimeBuilder:
    """Programmatic builder for Runtime DAGs.

    Usage:
        builder = RuntimeBuilder("my-pipeline")
        builder.add_module("obs", "ObservationCompiler", adapter="...ObservCompilerAdapter")
        builder.add_module("hyp", "HypothesisEngine", path="slow", trigger="checkpoint")
        builder.connect("obs", "hyp")
        builder.param("hyp", "min_support", 8)
        dag = builder.build()
        dag.save("config/runtime.yaml")
    """

    # Registry of known modules and their default adapters
    REGISTRY = {
        "observation_compiler": {
            "adapter": "core.agent.v4.runtime.adapter.ObservationCompilerAdapter",
            "default_path": "async",
            "default_trigger": "",
        },
        "hypothesis_engine": {
            "adapter": "core.agent.v4.runtime.adapter.HypothesisEngineAdapter",
            "default_path": "slow",
            "default_trigger": "checkpoint",
        },
        "skill_distiller": {
            "adapter": "core.agent.v4.runtime.adapter.SkillDistillerAdapter",
            "default_path": "deep",
            "default_trigger": "threshold",
        },
        "world_model": {
            "adapter": "core.agent.v4.runtime.adapter.WorldModelAdapter",
            "default_path": "slow",
            "default_trigger": "checkpoint",
        },
    }

    def __init__(self, name: str = "default"):
        self._name = name
        self._nodes: Dict[str, ModuleNode] = {}
        self._edges: List[DAGEdge] = []

    def add_module(
        self,
        name: str,
        module_type: str = None,
        adapter: str = None,
        path: str = None,
        timeout_ms: int = 5000,
        retry: int = 1,
        trigger: str = None,
        trigger_config: dict = None,
    ) -> "RuntimeBuilder":
        """Add a module node to the DAG.

        Args:
            name: Unique module instance name (e.g., "my_observer").
            module_type: Type key from REGISTRY or custom.
            adapter: Full dotted path to adapter class.
            path: Runtime path (async/slow/deep).
            timeout_ms: Execution timeout.
            retry: Number of retry attempts.
            trigger: Trigger type (event/checkpoint/threshold).
            trigger_config: Trigger configuration dict.
        """
        if module_type and module_type in self.REGISTRY:
            reg = self.REGISTRY[module_type]
            adapter = adapter or reg["adapter"]
            path = path or reg["default_path"]
            trigger = trigger if trigger is not None else reg["default_trigger"]

        self._nodes[name] = ModuleNode(
            name=name,
            adapter=adapter or "",
            timeout_ms=timeout_ms,
            retry=retry,
            params={},
            trigger=trigger or "",
            trigger_config=trigger_config or {},
            path=path or "async",
        )
        return self

    def connect(self, from_module: str, to_module: str) -> "RuntimeBuilder":
        """Add a directed edge between two modules."""
        self._edges.append(DAGEdge(from_module=from_module, to_module=to_module))
        return self

    def param(self, module: str, key: str, value: Any) -> "RuntimeBuilder":
        """Set a parameter for a module."""
        if module in self._nodes:
            self._nodes[module].params[key] = value
        return self

    def build(self) -> RuntimeDAG:
        """Build the RuntimeDAG."""
        return RuntimeDAG(
            name=self._name,
            nodes=list(self._nodes.values()),
            edges=list(self._edges),
        )

    def build_default_v4_dag(self) -> RuntimeDAG:
        """Build the default v4 pipeline DAG."""
        self.add_module("observation", "observation_compiler")
        self.add_module("hypothesis", "hypothesis_engine", path="slow",
                       trigger="checkpoint",
                       trigger_config={"event_count": 50, "time_minutes": 30})
        self.add_module("skill", "skill_distiller", path="deep",
                       trigger="threshold",
                       trigger_config={"pattern_count": 5, "success_rate": 0.9})
        self.connect("observation", "hypothesis")
        self.connect("hypothesis", "skill")
        self.param("hypothesis", "min_support", 8)
        self.param("hypothesis", "max_conflict", 3)
        return self.build()
