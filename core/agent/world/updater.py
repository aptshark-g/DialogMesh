from __future__ import annotations
"""IncrementalUpdater: hook git.commit events into CodeWorldAdapter."""

from typing import List, Optional, TYPE_CHECKING
from core.agent.v4.event_ir import EventIR


class IncrementalUpdater:
    """Listens for git.commit events and incrementally updates the World Graph.

    Hooks into EventBus. On git.commit, extracts changed files from
    the event payload and calls CodeWorldAdapter.incremental_update().
    """

    def __init__(self, adapter: "CodeWorldAdapter"):
        self._adapter = adapter
        self._update_count: int = 0

    def handle_event(self, event: EventIR) -> List[str]:
        """Process a single event. Returns affected unit IDs if it was a commit."""
        if event.kind != "git.commit":
            return []

        changed_files = event.payload.get("files", [])
        if isinstance(changed_files, str):
            changed_files = [changed_files]

        all_affected: List[str] = []
        for filepath in changed_files:
            if filepath.endswith(".py"):
                affected = self._adapter.incremental_update(filepath)
                all_affected.extend(affected)
                self._update_count += 1

        return all_affected

    @property
    def update_count(self) -> int:
        return self._update_count

    @property
    def graph(self):
        return self._adapter.graph


def parse_git_diff_files(diff_output: str) -> List[str]:
    """Parse git diff --name-only output into a list of changed files."""
    return [line.strip() for line in diff_output.strip().split("\n") if line.strip()]
