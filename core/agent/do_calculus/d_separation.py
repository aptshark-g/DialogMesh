"""d-separation testing for causal graphs."""
from .models import CausalSkeleton


class DSeparator:
    """Test whether X and Y are d-separated by a conditioning set."""

    def test(self, skeleton, x, y, conditioning_set=None):
        """Check if all paths between X and Y are blocked."""
        if conditioning_set is None:
            conditioning_set = []
        cond_set = set(conditioning_set)
        # If X or Y is in conditioning set, they are trivially separated from themselves
        if x == y:
            return x in cond_set

        # BFS over paths, tracking direction into each node
        visited = set()
        # Queue items: (current_node, previous_node, direction_into_current)
        from collections import deque
        queue = deque()
        # Initialize with all neighbors of x
        for edge in skeleton.edges:
            if edge.source == x:
                queue.append((edge.target, x, "out"))
            if edge.target == x:
                queue.append((edge.source, x, "in"))

        while queue:
            node, prev, direction = queue.popleft()
            if node == y:
                return False  # Found an open path
            key = (node, prev, direction)
            if key in visited:
                continue
            visited.add(key)

            # Explore next edges
            for edge in skeleton.edges:
                next_node = None
                next_dir = None
                if edge.source == node and edge.target != prev:
                    next_node = edge.target
                    next_dir = "out"
                elif edge.target == node and edge.source != prev:
                    next_node = edge.source
                    next_dir = "in"
                if next_node is None:
                    continue

                # Determine if this path is blocked at 'node'
                is_blocked = self._is_blocked(node, direction, next_dir, cond_set)
                if not is_blocked:
                    queue.append((next_node, node, next_dir))
        return True  # All paths blocked

    def _is_blocked(self, node, direction_in, direction_out, cond_set):
        """Check if the path through node is blocked."""
        in_cond = node in cond_set

        # Chain: A → B → C  or  A ← B ← C
        # At B: direction_in and direction_out are the same (both out or both in)
        is_chain = direction_in == direction_out
        # Fork: A ← B → C
        # At B: direction_in is "in", direction_out is "out"
        is_fork = (direction_in == "in" and direction_out == "out")
        # Collider: A → B ← C
        # At B: direction_in is "out", direction_out is "in"
        is_collider = (direction_in == "out" and direction_out == "in")

        if is_chain or is_fork:
            # Blocked if node is in conditioning set
            return in_cond
        elif is_collider:
            # Blocked unless node (or descendant) is in conditioning set
            # For simplicity, we only check node itself
            return not in_cond
        return False
