from .models import CausalSkeleton, BackdoorTestResult


class BackdoorCriterion:
    MAX_PATH_DEPTH = 5
    PROB_THRESHOLD = 0.95

    def verify(self, skeleton, x, y):
        paths = self._find_paths(skeleton, x, y)
        confounders = self._find_confounders(skeleton, paths)
        uncontrolled = [c for c in confounders if c not in skeleton.observed]
        verified = len(uncontrolled) == 0 and len(paths) > 0
        p = self._estimate_p(skeleton, x, y) if verified else 0.0
        return BackdoorTestResult(
            hypothesis=f"do({x}=0) => {y}=0",
            verified=verified,
            paths_checked=len(paths),
            confounders_found=uncontrolled,
            p_y_given_do_x=p,
        )

    def _find_paths(self, sk, x, y, depth=0, visited=None):
        if visited is None:
            visited = set()
        if depth > self.MAX_PATH_DEPTH:
            return []
        if x == y:
            return [[x]]
        visited = visited | {x}
        paths = []
        for edge in sk.edges:
            nxt = None
            if edge.source == x and edge.target not in visited:
                nxt = edge.target
            if edge.target == x and edge.source not in visited:
                nxt = edge.source
            if nxt:
                for p in self._find_paths(sk, nxt, y, depth + 1, visited):
                    paths.append([x] + p)
        return paths

    def _find_confounders(self, sk, paths):
        confounders = set()
        for path in paths:
            for node in path[1:-1]:
                parents = set()
                for e in sk.edges:
                    if e.target == node:
                        parents.add(e.source)
                if len(parents) >= 2:
                    confounders.add(node)
        return list(confounders)

    def _estimate_p(self, sk, x, y):
        for e in sk.edges:
            if e.source == x and e.target == y:
                return 1.0
        return 0.95 if self._find_paths(sk, x, y) else 0.5
