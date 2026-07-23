"""Topic Tree — tree-structured conversation memory with distance-decay granularity."""
from core.agent.topic_tree.fact_store import FactBlock, FactStore, RelationMetadataStore
from core.agent.topic_tree.heat_model import AdaptiveHeatModel
from core.agent.topic_tree.context import DualPerspectiveContext, MultiPerspectiveBranchView, BehaviorDrivenRefresh
from core.agent.topic_tree.manager import TopicTreeManager
