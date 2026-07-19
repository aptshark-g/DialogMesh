"""Git-style immutable version control for all editable system data.

Design: BUSINESS_CHAIN_09 §2
Each versioned object has a commit chain (SHA256-linked, append-only).
Used by: meta-cognition retrospection engine, rollback, audit.

Covered data types:
  - profile (OCEAN dimensions)
  - rules (ABC neuro-symbolic rules)
  - parameters (registry changes)
  - relations (association edge weights)
  - engineering (constraint revisions)
  - discourse_tree (node edits from chain 03)
  - inertia (pattern weight changes)
  - meta_decision (meta-cognition's own decisions)
"""
from __future__ import annotations
import hashlib, json, os, time, logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Commit:
    """Immutable version entry."""
    commit_id: str              # SHA256
    parent_id: str              # previous commit (empty for genesis)
    timestamp: float
    author: str                 # "user" | "meta_cognition" | "engine" | "abc_layer"
    operation: str              # "update" | "rollback" | "merge" | "split" | "create"
    target: str                 # "profile.C" | "rule.personality_t_type" | ...
    before: Any                 # value before
    after: Any                  # value after
    diff_summary: str           # human-readable diff (max 200 chars)
    reason: str                 # why this change
    verification: str = "pending"  # "pending" | "verified" | "rejected"

    def __post_init__(self):
        if not self.commit_id:
            payload = f"{self.parent_id}|{self.timestamp}|{self.target}|{self.after}"
            self.commit_id = hashlib.sha256(payload.encode()).hexdigest()[:16]


class VersionStore:
    """Append-only version log for one data type.
    
    Storage: data/versions/{category}.jsonl
    In-memory: latest values indexed for fast access.
    """

    def __init__(self, category: str, base_dir: str = "data/versions"):
        self.category = category
        self._path = f"{base_dir}/{category}.jsonl"
        self._commits: List[Commit] = []
        self._latest: Dict[str, Commit] = {}  # target → latest commit
        self._load()

    def commit(self, target: str, before: Any, after: Any, 
               author: str = "engine", reason: str = "", 
               operation: str = "update") -> Commit:
        """Record a change. Returns the commit."""
        parent = self._latest.get(target)
        parent_id = parent.commit_id if parent else ""
        
        c = Commit(
            commit_id="", parent_id=parent_id,
            timestamp=time.time(), author=author, operation=operation,
            target=target, before=str(before)[:200], after=str(after)[:200],
            diff_summary=f"{before} → {after}"[:200],
            reason=reason,
        )
        self._commits.append(c)
        self._latest[target] = c

        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "id": c.commit_id, "parent": c.parent_id, "ts": c.timestamp,
                "author": c.author, "op": c.operation, "target": c.target,
                "before": c.before, "after": c.after,
                "diff": c.diff_summary, "reason": c.reason, "verify": c.verification,
            }, ensure_ascii=False) + "\n")
        return c

    def latest(self, target: str) -> Optional[Commit]:
        return self._latest.get(target)

    def history(self, target: str, limit: int = 20) -> List[Commit]:
        """Get all versions of a target (traverse parent chain)."""
        result = []
        current = self._latest.get(target)
        visited = set()
        while current and len(result) < limit:
            if current.commit_id in visited: break
            visited.add(current.commit_id)
            result.append(current)
            # Find parent
            if current.parent_id:
                for c in reversed(self._commits):
                    if c.commit_id == current.parent_id:
                        current = c
                        break
                else:
                    break
            else:
                break
        return result

    def verify(self, target: str, verdict: str = "verified"):
        """Mark a commit as verified or rejected by meta-cognition."""
        c = self._latest.get(target)
        if c:
            c.verification = verdict

    def rollback_to(self, target: str, commit_id: str) -> Optional[Commit]:
        """Restore a target to a previous version (creates a new commit)."""
        target_commit = None
        for c in self._commits:
            if c.commit_id == commit_id:
                target_commit = c
                break
        if not target_commit: return None
        
        current = self._latest.get(target)
        return self.commit(
            target=target,
            before=current.after if current else "?",
            after=target_commit.after,
            author="meta_cognition",
            reason=f"rollback to {commit_id[:8]}",
            operation="rollback",
        )

    def diff(self, target: str, from_id: str, to_id: str = "") -> Dict:
        """Get before/after for retrospection."""
        commits = self.history(target, 50)
        from_c = to_c = None
        for c in commits:
            if c.commit_id == from_id: from_c = c
            if c.commit_id == to_id: to_c = c
        return {
            "target": target,
            "from": {"value": from_c.before if from_c else "?", "ts": from_c.timestamp if from_c else 0},
            "to": {"value": from_c.after if from_c else "?", "ts": from_c.timestamp if from_c else 0},
        }

    def stats(self) -> Dict:
        return {
            "total_commits": len(self._commits),
            "tracked_targets": len(self._latest),
            "by_author": {a: sum(1 for c in self._commits if c.author == a)
                         for a in set(c.author for c in self._commits)},
        }

    def _load(self):
        if not os.path.exists(self._path): return
        index = {}  # commit_id → Commit
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    c = Commit(
                        commit_id=d["id"], parent_id=d.get("parent", ""),
                        timestamp=d["ts"], author=d.get("author", "engine"),
                        operation=d.get("op", "update"), target=d["target"],
                        before=d.get("before"), after=d.get("after"),
                        diff_summary=d.get("diff", ""), reason=d.get("reason", ""),
                        verification=d.get("verify", "pending"),
                    )
                    self._commits.append(c)
                    index[c.commit_id] = c
                except Exception: pass
        # Rebuild latest index: last commit per target wins
        self._latest = {}
        for c in self._commits:
            self._latest[c.target] = c


class GlobalVersionControl:
    """Manages version stores for all data categories."""
    
    CATEGORIES = ["profile", "rules", "parameters", "relations",
                  "engineering", "discourse_tree", "inertia", "meta_decision"]

    def __init__(self, base_dir: str = "data/versions"):
        self._stores: Dict[str, VersionStore] = {}
        for cat in self.CATEGORIES:
            self._stores[cat] = VersionStore(cat, base_dir)

    def store(self, category: str) -> VersionStore:
        if category not in self._stores:
            self._stores[category] = VersionStore(category)
        return self._stores[category]

    def commit(self, category: str, target: str, before: Any, after: Any,
               author: str = "engine", reason: str = "") -> Commit:
        return self.store(category).commit(target, before, after, author, reason)

    def stats(self) -> Dict[str, Any]:
        return {cat: s.stats() for cat, s in self._stores.items()}
