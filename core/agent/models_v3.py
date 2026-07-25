"""DialogMesh v3.0 Unified Data Models — base layer.

ENGINEERING_DATA_MODEL §3.1: pure data containers, versioned fields, enum-first.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Any
import time
import uuid


# ═══ Base Mixins ═══

class VersionedMixin:
    """All models carry a version tag for serialization compatibility."""
    __version__: str = "3.0"


# ═══ Layer 0 — PCR ═══

class UserExpectation(Enum):
    TOOL = "tool"
    ADVISOR = "advisor"
    COMPANION = "companion"
    UNKNOWN = "unknown"


class ExecutionMode(Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


@dataclass
class PCRCognitiveSnapshot:
    """ENGINEERING_DATA_MODEL §4.2 — 4-dimension quick cognitive snapshot."""
    metacognition: float = 0.0   # input precision + self-referential language
    divergence: float = 0.0      # topic switching frequency + lexical diversity
    stability: float = 0.0       # expression style consistency
    confidence: float = 0.0      # inverse of modal verb frequency

    def __post_init__(self):
        for k in ("metacognition", "divergence", "stability", "confidence"):
            setattr(self, k, max(0.0, min(1.0, getattr(self, k))))


@dataclass
class PCROutput:
    """ENGINEERING_DATA_MODEL §4.1 — PCR routing output, control signal for downstream."""
    __version__: str = "3.0"
    expectation: UserExpectation = UserExpectation.UNKNOWN
    noise_level: float = 0.0
    complexity_level: float = 0.0
    cognitive_profile: PCRCognitiveSnapshot = field(default_factory=PCRCognitiveSnapshot)
    execution_mode: ExecutionMode = ExecutionMode.BALANCED
    parser_config_overrides: Dict[str, Any] = field(default_factory=dict)
    trace_log: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    session_id: Optional[str] = None

    def __post_init__(self):
        self.noise_level = max(0.0, min(1.0, self.noise_level))
        self.complexity_level = max(0.0, min(1.0, self.complexity_level))


# ═══ Layer 1 — Intent ═══

class IntentCategory(Enum):
    SCAN_MEMORY = "scan_memory"; READ_MEMORY = "read_memory"; WRITE_MEMORY = "write_memory"
    RESOLVE_POINTER = "resolve_pointer"
    DISASSEMBLE = "disassemble"; DECOMPILE = "decompile"; ANALYZE_PROTECTION = "analyze_protection"
    DEOBFUSCATE = "deobfuscate"; UNPACK = "unpack"
    SET_BREAKPOINT = "set_breakpoint"; GET_BREAKPOINT_HITS = "get_breakpoint_hits"
    TRACE_EXECUTION = "trace_execution"
    FIND_PATTERN = "find_pattern"; PATTERN_DETECT = "pattern_detect"
    BUILD_CFG = "build_cfg"; SYMBOLIC_EXECUTE = "symbolic_execute"; SOLVE_CONSTRAINTS = "solve_constraints"
    VERIFY_INPUT = "verify_input"
    ANALYZE_PROCESS = "analyze_process"; HACK_VALUE = "hack_value"
    FIND_FUNCTION = "find_function"; EXPLOIT_VULNERABILITY = "exploit_vulnerability"
    ASK_USER = "ask_user"; FINISH = "finish"; UNKNOWN = "unknown"; CHITCHAT = "chitchat"


class EntityType(Enum):
    MEMORY_ADDRESS = "memory_address"; POINTER_CHAIN = "pointer_chain"; MEMORY_SIZE = "memory_size"
    NUMERIC_VALUE = "numeric_value"; STRING_VALUE = "string_value"; BYTE_PATTERN = "byte_pattern"
    PROCESS_NAME = "process_name"; PID = "pid"; MODULE_NAME = "module_name"
    FUNCTION_NAME = "function_name"; SCAN_TYPE = "scan_type"; DATA_TYPE = "data_type"
    BREAKPOINT_ADDRESS = "breakpoint_address"; BREAKPOINT_TYPE = "breakpoint_type"
    SYMBOL_NAME = "symbol_name"; TIME_EXPRESSION = "time_expression"; CONDITION = "condition"


class AmbiguityType(Enum):
    MISSING_ENTITY = "missing_entity"; AMBIGUOUS_ENTITY = "ambiguous_entity"
    CONFLICTING_ENTITIES = "conflicting_entities"; VAGUE_SCOPE = "vague_scope"
    UNSUPPORTED_OPERATION = "unsupported_operation"; MULTIPLE_INTENTS = "multiple_intents"


@dataclass(frozen=True)
class Entity:
    """ENGINEERING_DATA_MODEL §5.2 — immutable entity reference."""
    type: EntityType
    value: Any
    raw_text: str = ""
    confidence: float = 1.0
    start_pos: int = -1
    end_pos: int = -1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            object.__setattr__(self, "confidence", max(0.0, min(1.0, self.confidence)))


@dataclass
class Ambiguity:
    """ENGINEERING_DATA_MODEL §5.3 — detected ambiguity requiring resolution."""
    type: AmbiguityType
    description: str
    affected_entities: List[EntityType] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    auto_resolvable: bool = False
    default_choice: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Intent:
    """ENGINEERING_DATA_MODEL §5.1 — Layer 1 core output."""
    __version__: str = "3.0"
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: Optional[str] = None
    category: IntentCategory = IntentCategory.UNKNOWN
    raw_input: str = ""
    normalized_input: str = ""
    entities: List[Entity] = field(default_factory=list)
    confidence: float = 0.0
    sub_intents: List["Intent"] = field(default_factory=list)
    requires_process: bool = True
    is_destructive: bool = False
    is_reversible: bool = False
    ambiguities: List[Ambiguity] = field(default_factory=list)
    temporal_constraint: Optional[str] = None
    scope_constraint: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_ambiguous(self) -> bool:
        return len(self.ambiguities) > 0 or len(self.sub_intents) > 1

    def get_entities(self, entity_type: EntityType) -> List[Entity]:
        return [e for e in self.entities if e.type == entity_type]

    def get_entity(self, entity_type: EntityType) -> Optional[Entity]:
        for e in self.entities:
            if e.type == entity_type:
                return e
        return None


# ═══ Layer 1.5 — Planning & Tools ═══

class TaskStatus(Enum):
    PENDING = "pending"; RUNNING = "running"; SUCCESS = "success"; FAILED = "failed"
    BLOCKED = "blocked"; CANCELLED = "cancelled"; SKIPPED = "skipped"
    NEEDS_CLARIFICATION = "needs_clarification"


class DependencyType(Enum):
    SEQUENTIAL = "sequential"; CONDITIONAL = "conditional"
    ITERATIVE = "iterative"; PARALLEL = "parallel"; FALLBACK = "fallback"


class ToolSource(Enum):
    BUILTIN = "builtin"; API_DOC = "api_doc"; MCP = "mcp"; CUSTOM = "custom"


class ToolType(Enum):
    LOCAL_FUNCTION = "local_function"; HTTP_API = "http_api"; MCP_REMOTE = "mcp_remote"


class SkillLevel(Enum):
    SKELETON = "skeleton"; STANDARD = "standard"; DETAILED = "detailed"


@dataclass
class TaskNode:
    """ENGINEERING_DATA_MODEL §6.2 — task graph node."""
    id: str = field(default_factory=lambda: f"T-{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    intent_id: Optional[str] = None
    layer: int = 1
    goal: str = ""
    strategy: str = ""
    tool_name: Optional[str] = None
    tool_params: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    alternative_strategies: List[str] = field(default_factory=list)
    fallback_nodes: List[str] = field(default_factory=list)
    estimated_cost: float = 1.0
    priority: int = 0
    tags: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    binding_confidence: Optional[float] = None
    binding_reason: Optional[str] = None

    def mark_running(self): self.status = TaskStatus.RUNNING; self.started_at = time.time()
    def mark_success(self, result): self.status = TaskStatus.SUCCESS; self.finished_at = time.time(); self.result = result
    def mark_failed(self, error): self.status = TaskStatus.FAILED; self.finished_at = time.time(); self.error = error
    def can_retry(self) -> bool: return self.retry_count < self.max_retries


@dataclass
class TaskEdge:
    """ENGINEERING_DATA_MODEL §6.3 — DAG edge."""
    source_id: str
    target_id: str
    dep_type: DependencyType = DependencyType.SEQUENTIAL
    condition: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolSchema:
    """ENGINEERING_DATA_MODEL §6.5 — standardized tool schema."""
    name: str
    description: str
    parameters: Dict[str, Any]
    required_params: List[str] = field(default_factory=list)
    source: ToolSource = ToolSource.BUILTIN
    tool_type: ToolType = ToolType.LOCAL_FUNCTION
    version: str = "1.0.0"
    tags: Set[str] = field(default_factory=set)
    endpoint_url: Optional[str] = None
    http_method: Optional[str] = None
    estimated_latency_ms: int = 100
    estimated_cost_tokens: int = 50
    requires_auth: bool = False
    auth_type: Optional[str] = None
    is_destructive: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def schema_hash(self) -> str:
        import hashlib, json
        return hashlib.sha256(json.dumps({"n": self.name, "p": self.parameters}, sort_keys=True).encode()).hexdigest()[:16]

    def to_llm_format(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


@dataclass
class PlanningSkill:
    """ENGINEERING_DATA_MODEL §6.6 — domain planning template."""
    skill_id: str
    name: str
    description: str
    version: str = "1.0.0"
    domain_tags: Set[str] = field(default_factory=set)
    intent_categories: Set[str] = field(default_factory=set)
    primitives: List[str] = field(default_factory=list)
    step_templates: List[Dict[str, Any]] = field(default_factory=list)
    tool_hints: Dict[str, List[str]] = field(default_factory=dict)
    constraints: List[Dict[str, Any]] = field(default_factory=list)
    level: SkillLevel = SkillLevel.STANDARD
    author: Optional[str] = None
    source: Optional[str] = None
    usage_count: int = 0
    success_rate: float = 0.0
    created_at: float = field(default_factory=time.time)
