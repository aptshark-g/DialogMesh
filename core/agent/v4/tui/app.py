"""DialogMesh v4 TUI — Textual terminal dashboard (Phase 1+2)."""
from __future__ import annotations
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, TabbedContent, TabPane, DataTable, Label
from textual.reactive import reactive
from textual.timer import Timer
import time


class DashboardTab(Static):
    """Runtime stats dashboard."""

    def on_mount(self):
        self.update_stats()

    def update_stats(self):
        try:
            from core.agent.v4.cli.main import _engine
            engine = _engine
        except Exception:
            engine = None

        lines = []
        lines.append("DialogMesh v4 Cognitive Runtime")
        lines.append("=" * 50)

        if engine is None:
            lines.append("  [red]Engine not started[/]")
        else:
            stats = engine.stats
            for path_name in ["async", "slow", "deep"]:
                s = stats.get(path_name)
                if s:
                    t = getattr(s, 'trigger_count', 0)
                    ok = getattr(s, 'success_count', 0)
                    fail = getattr(s, 'failure_count', 0)
                    bar = self._bar(ok, fail)
                    color = "green" if fail == 0 else "yellow"
                    lines.append(f"  [{color}]{path_name:<8s}[/] {bar} {t} triggers, {ok} ok, {fail} fail")

            # Observation pool
            pool = getattr(engine, '_observation_pool', None)
            if pool:
                bundles = pool.get_by_domain("all")
            else:
                bundles = []
            lines.append(f"  Observation Pool: {len(bundles)} bundles")

            # Context
            ctx = getattr(engine, '_last_context', None)
            if ctx:
                lines.append(f"  Last Context: {getattr(ctx, 'intent', '?')} ({getattr(ctx, 'total_items', 0)} items)")

        self.update("\n".join(lines))

    def _bar(self, ok: int, fail: int, width: int = 20) -> str:
        total = max(1, ok + fail)
        filled = int(ok / total * width)
        empty = width - filled
        return f"[{'#' * filled}{'.' * empty}]"


class ObservationsTab(Static):
    """Observation pool viewer."""

    def on_mount(self):
        self.update_data()

    def update_data(self):
        try:
            from core.agent.v4.cli.main import _engine
            engine = _engine
        except Exception:
            engine = None

        lines = ["Observations", "=" * 60]
        if engine is None:
            lines.append("[red]Engine not started[/]")
        else:
            pool = getattr(engine, '_observation_pool', None)
            if pool:
                bundles = pool.get_by_domain("all")[-15:]
                for b in bundles:
                    domain = str(getattr(b, 'domain', '?'))
                    summary = str(getattr(b, 'summary', str(b)))[:60]
                    lines.append(f"  [{domain:<12s}] {summary}")
            else:
                lines.append("  (no observations)")
        self.update("\n".join(lines))


class HypothesesTab(Static):
    """Hypothesis competition viewer."""

    def on_mount(self):
        self.update_data()

    def update_data(self):
        lines = ["Hypotheses (active only)", "=" * 60]
        try:
            from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline
            pipe = HypothesisPipeline()
            if hasattr(pipe, '_match_vote') and hasattr(pipe._match_vote, '_hypotheses'):
                for hid, h in list(pipe._match_vote._hypotheses.items())[:15]:
                    if h.status == "active":
                        bs = h.belief_state
                        s = bs['support']
                        c = bs['conflict']
                        st = bs['stability']
                        bar = "#" * min(10, int(s / 2))
                        lines.append(f"  [{h.domain:<12s}] {h.statement[:40]:<40s} S={s:<3d} C={c:<3d} Stab={st:.2f} {bar}")
            else:
                lines.append("  (no hypotheses available)")
        except Exception as e:
            lines.append(f"  [red]Error: {e}[/]")

        if len(lines) <= 2:
            lines.append("  (no active hypotheses)")
        self.update("\n".join(lines))


class KnowledgeTab(Static):
    """Frozen Knowledge viewer."""

    def on_mount(self):
        self.update_data()

    def update_data(self):
        lines = ["Knowledge Vault (frozen)", "=" * 60]
        try:
            from core.agent.v4.hypothesis_engine.pipeline import HypothesisPipeline
            pipe = HypothesisPipeline()
            if hasattr(pipe, '_match_vote') and hasattr(pipe._match_vote, '_hypotheses'):
                count = 0
                for hid, h in pipe._match_vote._hypotheses.items():
                    if h.status == "frozen":
                        lines.append(f"  [{h.domain:<12s}] {h.statement[:45]:<45s} score={h.belief_score():.2f}")
                        count += 1
                        if count >= 15:
                            break
                if count == 0:
                    lines.append("  (no frozen knowledge)")
            else:
                lines.append("  (not available)")
        except Exception as e:
            lines.append(f"  [red]Error: {e}[/]")
        self.update("\n".join(lines))


class SkillsTab(Static):
    """Skill forge viewer."""

    def on_mount(self):
        self.update_data()

    def update_data(self):
        lines = ["Skill Forge", "=" * 60]
        try:
            from core.agent.v4.skill_layer.skill_pool import SkillPool
            pool = SkillPool()
            skills = pool.list_all() if hasattr(pool, 'list_all') else []
            if skills:
                for s in skills[:15]:
                    name = getattr(s, 'name', str(s))[:25]
                    domain = getattr(s, 'domain', '?')[:12]
                    usage = getattr(s, 'usage_count', 0)
                    status = getattr(s, 'status', '?')
                    color = "green" if status == "verified" else "yellow"
                    lines.append(f"  [{color}]{name:<25s}[/] {domain:<12s} usage={usage} {status}")
            else:
                lines.append("  (no skills)")
        except Exception as e:
            lines.append(f"  [red]Error: {e}[/]")
        self.update("\n".join(lines))


class WorldTab(Static):
    """World Graph viewer."""

    def on_mount(self):
        self.update_data()

    def update_data(self):
        lines = ["Semantic World Model", "=" * 60]
        try:
            from core.agent.v4.cli.main import _engine
            engine = _engine
            world_graph = getattr(engine, '_world_graph', None) if engine else None
        except Exception:
            world_graph = None

        if world_graph is None:
            lines.append("  [yellow]World Graph not loaded[/]")
            lines.append("  Use: engine._world_graph = CodeWorldAdapter().build_graph('.')")
        else:
            lines.append(f"  Graph: {world_graph.world} ({world_graph.node_count} nodes, {world_graph.edge_count} edges)")
            lines.append(f"  Communities: {len(world_graph.communities)}")

            # Top backbone
            ranked = sorted(world_graph.backbone.items(), key=lambda x: x[1], reverse=True)[:8]
            lines.append("  Top Backbone:")
            for uid, score in ranked:
                node = world_graph.get_unit(uid)
                name = node.name if node else uid
                bar = "#" * int(score * 20)
                lines.append(f"    {bar} {score:.2f}  {name[:30]}")

            # Communities summary
            lines.append(f"  Communities ({len(world_graph.communities)}):")
            for cid, units in list(world_graph.communities.items())[:5]:
                lines.append(f"    {cid}: {len(units)} nodes")
        self.update("\n".join(lines))


class DialogMeshTUI(App):
    """DialogMesh v4 Terminal Dashboard."""

    CSS = """
    DashboardTab { height: 1fr; }
    ObservationsTab { height: 1fr; }
    HypothesesTab { height: 1fr; }
    """

    TITLE = "DialogMesh v4 — Terminal Dashboard"

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Dashboard", id="dash"):
                yield DashboardTab(id="dash-content")
            with TabPane("Observations", id="obs"):
                yield ObservationsTab(id="obs-content")
            with TabPane("Hypotheses", id="hyp"):
                yield HypothesesTab(id="hyp-content")
            with TabPane("Knowledge", id="know"):
                yield KnowledgeTab(id="know-content")
            with TabPane("Skills", id="skill"):
                yield SkillsTab(id="skill-content")
            with TabPane("World", id="world"):
                yield WorldTab(id="world-content")
            with TabPane("Context", id="ctx"):
                yield Static("Context / Event Log panels — Phase 3")
        yield Footer()

    def on_mount(self):
        # Start engine if not started
        try:
            from core.agent.v4.cli.main import _engine
            if _engine is None:
                from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
                import core.agent.v4.cli.main as cm
                cm._engine = CognitiveRuntimeEngine()
                cm._engine.start()
        except Exception:
            pass

        # Refresh every second
        self._timer = self.set_interval(1, self.refresh_all)

    def refresh_all(self):
        dash = self.query_one("#dash-content", DashboardTab)
        if dash:
            dash.update_stats()
        obs = self.query_one("#obs-content", ObservationsTab)
        if obs:
            obs.update_data()
        hyp = self.query_one("#hyp-content", HypothesesTab)
        if hyp:
            hyp.update_data()
        know = self.query_one("#know-content", KnowledgeTab)
        if know:
            know.update_data()
        skill = self.query_one("#skill-content", SkillsTab)
        if skill:
            skill.update_data()
        world = self.query_one("#world-content", WorldTab)
        if world:
            world.update_data()

    def on_unmount(self):
        try:
            from core.agent.v4.cli.main import _engine
            if _engine:
                _engine.stop()
        except Exception:
            pass


def main():
    app = DialogMeshTUI()
    app.run()


if __name__ == "__main__":
    main()
