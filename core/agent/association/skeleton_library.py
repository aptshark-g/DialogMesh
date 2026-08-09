from dataclasses import dataclass, field
from .models import MetaRole, CausalConstraints

@dataclass
class CausalSkeleton:
    name: str; roles: list; requires: list = field(default_factory=list)
    desc: str = ""

class SkeletonLibrary:
    """Causal skeleton library — 20 common patterns (D-9, ENGINEERING_V3_3).

    Each skeleton is an ordered combination of meta-roles plus the constraint
    fields it requires. ``SkeletonMatcher`` scores candidates by how many of
    the required constraints the extracted ``CausalConstraints`` satisfies.
    """

    def __init__(self):
        self.skeletons = [
            CausalSkeleton("source_dissipate", [MetaRole.SOURCE, MetaRole.DISSIPATE, MetaRole.SINK], ["involves_dissipation"]),
            CausalSkeleton("source_store", [MetaRole.SOURCE, MetaRole.STORE_P, MetaRole.SINK], ["involves_storage"]),
            CausalSkeleton("source_transform", [MetaRole.SOURCE, MetaRole.TRANSFORM, MetaRole.SINK], ["involves_transformation"]),
            CausalSkeleton("feedback", [MetaRole.SOURCE, MetaRole.TRANSFORM, MetaRole.SINK, MetaRole.SOURCE], ["has_feedback"]),
            CausalSkeleton("parallel", [MetaRole.SOURCE, MetaRole.JSPLIT, MetaRole.TRANSFORM, MetaRole.JSUM, MetaRole.SINK]),
            # D-9 extensions (ENGINEERING_V3_3 §5: buffered/cascade/feedback variants)
            CausalSkeleton(
                "buffered_flow",
                [MetaRole.SOURCE, MetaRole.STORE_K, MetaRole.TRANSFORM, MetaRole.SINK],
                ["involves_storage"],
                "source -> buffer(queue) -> transform -> sink",
            ),
            CausalSkeleton(
                "cascade_transform",
                [MetaRole.SOURCE, MetaRole.TRANSFORM, MetaRole.TRANSFORM, MetaRole.SINK],
                ["involves_transformation"],
                "multi-step transform chain",
            ),
            CausalSkeleton(
                "storage_dissipate",
                [MetaRole.SOURCE, MetaRole.STORE_P, MetaRole.DISSIPATE, MetaRole.SINK],
                ["involves_storage", "involves_dissipation"],
                "stored potential then dissipated",
            ),
            CausalSkeleton(
                "feedback_dissipate",
                [MetaRole.SOURCE, MetaRole.TRANSFORM, MetaRole.DISSIPATE, MetaRole.SINK, MetaRole.SOURCE],
                ["has_feedback", "involves_dissipation"],
                "feedback loop with dissipation",
            ),
            CausalSkeleton(
                "feedback_storage",
                [MetaRole.SOURCE, MetaRole.STORE_P, MetaRole.TRANSFORM, MetaRole.SINK, MetaRole.SOURCE],
                ["has_feedback", "involves_storage"],
                "feedback loop with storage",
            ),
            CausalSkeleton(
                "parallel_dissipate",
                [MetaRole.SOURCE, MetaRole.JSPLIT, MetaRole.TRANSFORM, MetaRole.DISSIPATE, MetaRole.JSUM, MetaRole.SINK],
                ["involves_dissipation"],
                "parallel branches with dissipation",
            ),
            CausalSkeleton(
                "parallel_storage",
                [MetaRole.SOURCE, MetaRole.JSPLIT, MetaRole.STORE_P, MetaRole.TRANSFORM, MetaRole.JSUM, MetaRole.SINK],
                ["involves_storage"],
                "parallel branches with storage",
            ),
            CausalSkeleton(
                "split_merge",
                [MetaRole.SOURCE, MetaRole.JSPLIT, MetaRole.JSUM, MetaRole.SINK],
                [],
                "split then merge without transform",
            ),
            CausalSkeleton(
                "accumulate_transform",
                [MetaRole.SOURCE, MetaRole.STORE_K, MetaRole.STORE_P, MetaRole.TRANSFORM, MetaRole.SINK],
                ["involves_storage", "involves_transformation"],
                "queue accumulation then transform",
            ),
            CausalSkeleton(
                "cascade_feedback",
                [MetaRole.SOURCE, MetaRole.TRANSFORM, MetaRole.TRANSFORM, MetaRole.SINK, MetaRole.SOURCE],
                ["has_feedback", "involves_transformation"],
                "cascade transform with feedback",
            ),
            CausalSkeleton(
                "dissipative_transform",
                [MetaRole.SOURCE, MetaRole.TRANSFORM, MetaRole.DISSIPATE, MetaRole.SINK],
                ["involves_transformation", "involves_dissipation"],
                "transform with partial loss",
            ),
            CausalSkeleton(
                "storage_feedback_dissipate",
                [MetaRole.SOURCE, MetaRole.STORE_P, MetaRole.TRANSFORM, MetaRole.DISSIPATE, MetaRole.SINK, MetaRole.SOURCE],
                ["has_feedback", "involves_storage", "involves_dissipation"],
                "storage + feedback + dissipation",
            ),
            CausalSkeleton(
                "multi_source_merge",
                [MetaRole.SOURCE, MetaRole.JSUM, MetaRole.SINK],
                [],
                "multiple sources converge to one sink",
            ),
            CausalSkeleton(
                "multi_sink_split",
                [MetaRole.SOURCE, MetaRole.JSPLIT, MetaRole.SINK],
                [],
                "one source fans out to multiple sinks",
            ),
            CausalSkeleton(
                "reservoir_cycle",
                [MetaRole.SOURCE, MetaRole.STORE_K, MetaRole.STORE_P, MetaRole.SINK, MetaRole.SOURCE],
                ["has_feedback", "involves_storage"],
                "storage reservoir with recirculation",
            ),
        ]
    def query(self, constraints):
        scored = []
        for sk in self.skeletons:
            matches = sum(1 for r in sk.requires if getattr(constraints, r, False))
            total = len(sk.requires) if sk.requires else 1
            scored.append((sk, matches / total))
        scored.sort(key=lambda x: -x[1])
        return [s[0] for s in scored[:5]]
