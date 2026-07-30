"""Engineering knowledge — re-exports from canonical locations."""
from core.agent.engineering.models import ArtifactType, EdgeType, KnowledgeType, ArtifactEdge
from core.agent.engineering.registry import ArtifactRegistry
from core.agent.engineering.knowledge_graph import KnowledgeGraph
from core.agent.engineering.constraint_engine import ConstraintEngine

# NOTE: v3_2 engineering_chain merged here. Tests use direct imports above.
