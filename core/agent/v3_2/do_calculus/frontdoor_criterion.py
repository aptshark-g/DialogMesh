"""Front-door criterion identification."""
from .models import CausalSkeleton


class FrontdoorCriterion:
    """Find mediator M and check X→M→Y with no confounding."""

    def identify(self, skeleton, x, y):
        """Try to identify P(y|do(x)) via front-door."""
        # Find all mediators M such that X→M and M→Y
        mediators = []
        for edge in skeleton.edges:
            if edge.source == x and edge.target != y:
                m = edge.target
                # Check M→Y
                has_m_to_y = any(e.source == m and e.target == y for e in skeleton.edges)
                if has_m_to_y:
                    mediators.append(m)

        for m in mediators:
            # Check no unblocked backdoor path X←...→M
            if not self._has_backdoor(skeleton, x, m):
                # Check no unblocked backdoor path M←...→Y
                if not self._has_backdoor(skeleton, m, y):
                    return True, m, f"Front-door via M={m}: X→M→Y, no confounding."
        return False, None, "Front-door identification failed."

    def _has_backdoor(self, skeleton, a, b):
        """Check if there is any backdoor path between a and b."""
        # Backdoor path = path with an arrow into a (i.e., starts with parent of a)
        parents_of_a = [e.source for e in skeleton.edges if e.target == a]
        visited = set()
        stack = [(p, a) for p in parents_of_a]
        while stack:
            prev, curr = stack.pop()
            if curr == b:
                return True
            if (prev, curr) in visited:
                continue
            visited.add((prev, curr))
            for edge in skeleton.edges:
                if edge.source == curr and edge.target != prev and edge.target != a:
                    stack.append((curr, edge.target))
                if edge.target == curr and edge.source != prev and edge.source != a:
                    stack.append((curr, edge.source))
        return False
