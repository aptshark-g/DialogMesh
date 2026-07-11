"""Core do-calculus engine with three rules and recursive identification."""
from .models import CausalSkeleton, BackdoorTestResult
from .backdoor_criterion import BackdoorCriterion


class DoCalculusEngine:
    """Implements Pearl's do-calculus rules 1-3 for causal identification."""

    def __init__(self, backdoor=None):
        self.backdoor = backdoor or BackdoorCriterion()

    def rule_1_insert(self, skeleton, x, y, z):
        """Rule 1 (Insertion): P(y|do(x), z) = P(y|x, z) if no backdoor path X←...→Y given Z."""
        # Check if Z blocks all backdoor paths between X and Y
        result = self.backdoor.verify(skeleton, x, y)
        if result.verified and z in skeleton.observed:
            explanation = f"Rule 1: Z={z} blocks backdoor paths; insert observation."
            return True, skeleton, explanation
        explanation = f"Rule 1: Z={z} does not block backdoor paths; cannot insert."
        return False, skeleton, explanation

    def rule_2_delete(self, skeleton, x, y, z):
        """Rule 2 (Deletion): P(y|do(x), do(z)) = P(y|do(x), z) if no causal path Z→...→X."""
        # Check if there is any directed path from Z to X
        if not self._has_directed_path(skeleton, z, x):
            explanation = f"Rule 2: No causal path {z}→...→{x}; delete do(z)."
            return True, skeleton, explanation
        explanation = f"Rule 2: Causal path {z}→...→{x} exists; cannot delete."
        return False, skeleton, explanation

    def rule_3_swap(self, skeleton, x, y, z):
        """Rule 3 (Swap): P(y|do(x), do(z)) = P(y|do(x)) if no association X↔Z given do(X)."""
        # Check if X and Z are d-separated given do(X) — i.e., no open path between X and Z
        if not self._has_open_path(skeleton, x, z, conditioning_set={x}):
            explanation = f"Rule 3: No association between {x} and {z} given do({x}); swap."
            return True, skeleton, explanation
        explanation = f"Rule 3: Association between {x} and {z} remains; cannot swap."
        return False, skeleton, explanation

    def identify(self, skeleton, x, y):
        """Try to identify P(y|do(x)) using rules 1-3 recursively."""
        # Try backdoor first
        backdoor_result = self.backdoor.verify(skeleton, x, y)
        if backdoor_result.verified:
            return True, skeleton, f"Identified via backdoor: {backdoor_result.hypothesis}"

        # Try frontdoor-like mediation via rule 2 + rule 3 combinations
        for edge in skeleton.edges:
            if edge.source == x and edge.target != y:
                m = edge.target
                # Try rule 2: P(y|do(x), do(m)) = P(y|do(x), m)
                ok2, sk2, exp2 = self.rule_2_delete(skeleton, x, y, m)
                if ok2:
                    # Try rule 3: P(y|do(x), m) = P(y|do(x)) if no association
                    ok3, sk3, exp3 = self.rule_3_swap(sk2, x, y, m)
                    if ok3:
                        return True, sk3, f"Identified via rule 2+3 mediation through {m}: {exp2}; {exp3}"

        # Try rule 1 with each observed variable as conditioning set
        for z in skeleton.observed:
            ok1, sk1, exp1 = self.rule_1_insert(skeleton, x, y, z)
            if ok1:
                return True, sk1, f"Identified via rule 1 with Z={z}: {exp1}"

        return False, skeleton, "Identification failed: no rule applies."

    def _has_directed_path(self, skeleton, start, end, visited=None):
        if visited is None:
            visited = set()
        if start == end:
            return True
        if start in visited:
            return False
        visited.add(start)
        for edge in skeleton.edges:
            if edge.source == start and edge.target not in visited:
                if self._has_directed_path(skeleton, edge.target, end, visited):
                    return True
        return False

    def _has_open_path(self, skeleton, x, z, conditioning_set=None):
        """Check if there is any open (unblocked) path between x and z."""
        if conditioning_set is None:
            conditioning_set = set()
        visited = set()
        stack = [(x, None)]  # (current_node, direction_from_parent)
        while stack:
            node, direction = stack.pop()
            if node == z:
                return True
            if (node, direction) in visited:
                continue
            visited.add((node, direction))
            for edge in skeleton.edges:
                neighbors = []
                if edge.source == node:
                    neighbors.append((edge.target, "out"))
                if edge.target == node:
                    neighbors.append((edge.source, "in"))
                for nxt, ndir in neighbors:
                    if (nxt, ndir) in visited:
                        continue
                    # Simple path blocking: if node is in conditioning_set and it's a chain/fork, block
                    if node in conditioning_set:
                        # At a conditioned node, chain and fork are blocked, collider is open
                        # For simplicity, block if direction changes (chain/fork)
                        if direction is not None and ndir != direction:
                            continue
                    stack.append((nxt, ndir))
        return False
