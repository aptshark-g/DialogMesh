from dataclasses import dataclass, field
from .models import MetaRole, CausalConstraints

@dataclass
class CausalSkeleton:
    name: str; roles: list; requires: list = field(default_factory=list)
    desc: str = ""

class SkeletonLibrary:
    def __init__(self):
        self.skeletons = [
            CausalSkeleton("source_dissipate", [MetaRole.SOURCE, MetaRole.DISSIPATE, MetaRole.SINK], ["involves_dissipation"]),
            CausalSkeleton("source_store", [MetaRole.SOURCE, MetaRole.STORE_P, MetaRole.SINK], ["involves_storage"]),
            CausalSkeleton("source_transform", [MetaRole.SOURCE, MetaRole.TRANSFORM, MetaRole.SINK], ["involves_transformation"]),
            CausalSkeleton("feedback", [MetaRole.SOURCE, MetaRole.TRANSFORM, MetaRole.SINK, MetaRole.SOURCE], ["has_feedback"]),
            CausalSkeleton("parallel", [MetaRole.SOURCE, MetaRole.JSPLIT, MetaRole.TRANSFORM, MetaRole.JSUM, MetaRole.SINK]),
        ]
    def query(self, constraints):
        scored = []
        for sk in self.skeletons:
            matches = sum(1 for r in sk.requires if getattr(constraints, r, False))
            total = len(sk.requires) if sk.requires else 1
            scored.append((sk, matches / total))
        scored.sort(key=lambda x: -x[1])
        return [s[0] for s in scored[:5]]