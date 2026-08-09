"""DialogMesh v4 TUI — Textual terminal dashboard (Dual-mode: API + Offline).

Architecture:
    DataSource ──► API mode (localhost:8000)
            └──► Offline mode (direct engine import)
            └──► None mode (degraded, read-only)

Tabs (9):
    1.Dashboard  2.Observations  3.Hypotheses  4.Knowledge
    5.Skills     6.World        7.Context     8.Event Log  9.Settings

Keyboard:
    1-9      Tab switching
    r        Refresh all
    e        Language: English
    z        Language: Chinese
    F10/q    Quit
"""
from __future__ import annotations
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header, Footer, Static, TabbedContent, TabPane,
    DataTable, Label, ProgressBar, Tree
)
from textual.reactive import reactive
from textual.timer import Timer
import time, os, logging
from i18n import load_locale, t as _t

from tools.tui.data_source import DataSource, DataResult

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Helper: safe t() wrapper
# ═══════════════════════════════════════════════════════════════

def t(key: str, **kwargs) -> str:
    """Safe translation — returns key if missing."""
    try:
        return _t(key, **kwargs)
    except Exception:
        return key


# ═══════════════════════════════════════════════════════════════
# Tab 1: Dashboard
# ═══════════════════════════════════════════════════════════════

class DashboardTab(Static):
    """Runtime stats dashboard with mode indicator."""

    def __init__(self, data_source: DataSource, **kwargs):
        super().__init__(**kwargs)
        self.ds = data_source

    def on_mount(self):
        self.update_stats()

    def update_stats(self):
        lines = []
        lines.append(t("tui.dashboard.title"))
        lines.append("=" * 50)
        lines.append(f"  [cyan]Mode: {self.ds.mode.upper()}[/]")
        lines.append("")

        result = self.ds.get_status()
        if not result.ok:
            lines.append(f"  [red]{result.error or t('tui.dashboard.engine_off')}[/]")
        else:
            data = result.data or {}
            for path_name in ["async", "slow", "deep"]:
                s = data.get(path_name, {})
                if s:
                    tc = s.get('trigger_count', 0)
                    ok = s.get('success_count', 0)
                    fail = s.get('failure_count', 0)
                    bar = self._bar(ok, fail)
                    color = "green" if fail == 0 else "yellow"
                    lines.append(f"  [{color}]{path_name:<8s}[/] {bar} {tc} triggers, {ok} ok, {fail} fail")
                else:
                    lines.append(f"  [dim]{path_name:<8s}[/] (no data)")

            # Observation pool
            obs_result = self.ds.get_observations(limit=1)
            count = obs_result.data.get("count", 0) if obs_result.ok else 0
            lines.append(t("tui.dashboard.obs_pool", count=count))

            # Context
            ctx_result = self.ds.get_context()
            if ctx_result.ok and ctx_result.data:
                intent = ctx_result.data.get("intent", "?")
                total = ctx_result.data.get("total_items", 0)
                lines.append(f"  Last Context: {intent} ({total} items)")

        self.update("\n".join(lines))

    def _bar(self, ok: int, fail: int, width: int = 20) -> str:
        total = max(1, ok + fail)
        filled = int(ok / total * width)
        empty = width - filled
        return f"[{'█' * filled}{'░' * empty}]"


# ═══════════════════════════════════════════════════════════════
# Tab 2: Observations (DataTable)
# ═══════════════════════════════════════════════════════════════

class ObservationsTab(Container):
    """Observation pool viewer with DataTable."""

    def __init__(self, data_source: DataSource, **kwargs):
        super().__init__(**kwargs)
        self.ds = data_source
        self._table: DataTable | None = None

    def compose(self) -> ComposeResult:
        yield Label(t("tui.observations.title"))
        yield DataTable(id="obs-table")

    def on_mount(self):
        table = self.query_one("#obs-table", DataTable)
        table.add_columns("ID", "Domain", "Summary", "Time")
        table.cursor_type = "row"
        self.update_data()

    def update_data(self):
        table = self.query_one("#obs-table", DataTable)
        table.clear()
        result = self.ds.get_observations(limit=50)
        if not result.ok:
            table.add_row("[red]Error", result.error or "No data", "", "")
            return

        items = result.data.get("items", []) if result.data else []
        if not items:
            table.add_row("(no observations)", "", "", "")
            return

        for item in items:
            table.add_row(
                item.get("id", "?")[:16],
                item.get("domain", "?")[:12],
                item.get("summary", "")[:50],
                item.get("timestamp", "")[:8],
            )


# ═══════════════════════════════════════════════════════════════
# Tab 3: Hypotheses (DataTable)
# ═══════════════════════════════════════════════════════════════

class HypothesesTab(Container):
    """Hypothesis competition viewer with DataTable."""

    def __init__(self, data_source: DataSource, **kwargs):
        super().__init__(**kwargs)
        self.ds = data_source

    def compose(self) -> ComposeResult:
        yield Label(t("tui.hypotheses.title"))
        yield DataTable(id="hyp-table")

    def on_mount(self):
        table = self.query_one("#hyp-table", DataTable)
        table.add_columns("ID", "Domain", "Statement", "S", "C", "Stab")
        table.cursor_type = "row"
        self.update_data()

    def update_data(self):
        table = self.query_one("#hyp-table", DataTable)
        table.clear()
        result = self.ds.get_hypotheses(limit=50, status="active")
        if not result.ok:
            table.add_row("[red]Error", result.error or "No data", "", "", "", "")
            return

        items = result.data.get("items", []) if result.data else []
        if not items:
            table.add_row("(no active hypotheses)", "", "", "", "", "")
            return

        for item in items:
            stab = item.get("stability", 0)
            color = "green" if stab > 0.8 else "yellow" if stab > 0.5 else "red"
            table.add_row(
                item.get("id", "?")[:12],
                item.get("domain", "?")[:10],
                item.get("statement", "")[:40],
                str(item.get("support", 0)),
                str(item.get("conflict", 0)),
                f"[{color}]{stab:.2f}[/{color}]",
            )


# ═══════════════════════════════════════════════════════════════
# Tab 4: Knowledge (DataTable)
# ═══════════════════════════════════════════════════════════════

class KnowledgeTab(Container):
    """Frozen Knowledge viewer with DataTable."""

    def __init__(self, data_source: DataSource, **kwargs):
        super().__init__(**kwargs)
        self.ds = data_source

    def compose(self) -> ComposeResult:
        yield Label(t("tui.knowledge.title"))
        yield DataTable(id="know-table")

    def on_mount(self):
        table = self.query_one("#know-table", DataTable)
        table.add_columns("ID", "Domain", "Statement", "Score")
        table.cursor_type = "row"
        self.update_data()

    def update_data(self):
        table = self.query_one("#know-table", DataTable)
        table.clear()
        result = self.ds.get_knowledge(limit=50)
        if not result.ok:
            table.add_row("[red]Error", result.error or "No data", "", "")
            return

        items = result.data.get("items", []) if result.data else []
        if not items:
            table.add_row("(no frozen knowledge)", "", "", "")
            return

        for item in items:
            score = item.get("score", 0)
            color = "green" if score > 0.8 else "yellow" if score > 0.6 else "white"
            table.add_row(
                item.get("id", "?")[:12],
                item.get("domain", "?")[:10],
                item.get("statement", "")[:40],
                f"[{color}]{score:.2f}[/{color}]",
            )


# ═══════════════════════════════════════════════════════════════
# Tab 5: Skills (DataTable)
# ═══════════════════════════════════════════════════════════════

class SkillsTab(Container):
    """Skill forge viewer with DataTable."""

    def __init__(self, data_source: DataSource, **kwargs):
        super().__init__(**kwargs)
        self.ds = data_source

    def compose(self) -> ComposeResult:
        yield Label(t("tui.skills.title"))
        yield DataTable(id="skill-table")

    def on_mount(self):
        table = self.query_one("#skill-table", DataTable)
        table.add_columns("Name", "Domain", "Usage", "Status")
        table.cursor_type = "row"
        self.update_data()

    def update_data(self):
        table = self.query_one("#skill-table", DataTable)
        table.clear()
        result = self.ds.get_skills(limit=50)
        if not result.ok:
            table.add_row("[red]Error", result.error or "No data", "", "")
            return

        items = result.data.get("items", []) if result.data else []
        if not items:
            table.add_row("(no skills)", "", "", "")
            return

        for item in items:
            status = item.get("status", "?")
            color = "green" if status == "verified" else "yellow" if status == "candidate" else "white"
            table.add_row(
                item.get("name", "?")[:25],
                item.get("domain", "?")[:10],
                str(item.get("usage", 0)),
                f"[{color}]{status}[/{color}]",
            )


# ═══════════════════════════════════════════════════════════════
# Tab 6: World
# ═══════════════════════════════════════════════════════════════

class WorldTab(Static):
    """World Graph viewer."""

    def __init__(self, data_source: DataSource, **kwargs):
        super().__init__(**kwargs)
        self.ds = data_source

    def on_mount(self):
        self.update_data()

    def update_data(self):
        lines = [t("tui.world.title"), "=" * 60]
        result = self.ds.get_world()
        if not result.ok:
            lines.append(f"[red]{result.error or t('tui.world.not_loaded')}[/]")
            lines.append(t("tui.world.usage_hint"))
        else:
            data = result.data or {}
            lines.append(t("tui.graph.stats",
                world=data.get("world", "?"),
                nodes=data.get("nodes", 0),
                edges=data.get("edges", 0)))
            lines.append(f"  Communities: {data.get('communities', 0)}")

            # Top backbone
            backbone = data.get("backbone", [])
            if backbone:
                lines.append(t("tui.world.top_backbone"))
                for uid, score in backbone[:8]:
                    bar = "█" * int(score * 20)
                    lines.append(f"    {bar} {score:.2f}  {uid[:30]}")

            # Communities summary
            lines.append(t("tui.world.communities", count=data.get("communities", 0)))
        self.update("\n".join(lines))


# ═══════════════════════════════════════════════════════════════
# Tab 7: Context
# ═══════════════════════════════════════════════════════════════

class ContextTab(Static):
    """CrossDomainContextIR viewer."""

    def __init__(self, data_source: DataSource, **kwargs):
        super().__init__(**kwargs)
        self.ds = data_source

    def on_mount(self):
        self.update_data()

    def update_data(self):
        lines = [t("tui.context.title"), "=" * 60]
        result = self.ds.get_context()
        if not result.ok:
            lines.append(f"[red]{result.error or t('tui.context.no_data')}[/]")
            lines.append(t("tui.context.send_hint"))
        else:
            data = result.data or {}
            intent = data.get("intent", "?")
            total = data.get("total_items", 0)
            lines.append(t("tui.context.intent", intent=intent, total=total))

            sources = data.get("sources", {})
            if sources:
                for src, count in sorted(sources.items(), key=lambda x: -x[1]):
                    lines.append(f"  [{src}] {count} items")
            elif total > 0:
                lines.append(f"  (structured IR with {total} items)")
            else:
                lines.append(t("tui.context.no_data"))
        self.update("\n".join(lines))


# ═══════════════════════════════════════════════════════════════
# Tab 8: Event Log (DataTable)
# ═══════════════════════════════════════════════════════════════

class EventLogTab(Container):
    """Event log viewer with DataTable."""

    def __init__(self, data_source: DataSource, **kwargs):
        super().__init__(**kwargs)
        self.ds = data_source

    def compose(self) -> ComposeResult:
        yield Label(t("tui.events.title"))
        yield DataTable(id="evt-table")

    def on_mount(self):
        table = self.query_one("#evt-table", DataTable)
        table.add_columns("Event ID", "Kind", "Preview")
        table.cursor_type = "row"
        self.update_data()

    def update_data(self):
        table = self.query_one("#evt-table", DataTable)
        table.clear()
        result = self.ds.get_events(limit=30)
        if not result.ok:
            table.add_row("[red]Error", result.error or "No data", "")
            return

        data = result.data or {}
        items = data.get("items", [])
        total = data.get("total", 0)
        unconsumed = data.get("unconsumed", 0)

        # Header row
        table.add_row(
            f"[dim]Total: {total}[/]",
            f"[dim]Unconsumed: {unconsumed}[/]",
            "",
        )

        if not items:
            table.add_row("(no events)", "", "")
            return

        for item in items:
            table.add_row(
                item.get("event_id", "?")[:20],
                item.get("kind", "?")[:18],
                item.get("payload_preview", "")[:40],
            )


# ═══════════════════════════════════════════════════════════════
# Tab 9: Settings
# ═══════════════════════════════════════════════════════════════

class SettingsTab(Static):
    """Settings panel with language switcher and mode info."""

    def __init__(self, data_source: DataSource, **kwargs):
        super().__init__(**kwargs)
        self.ds = data_source

    def on_mount(self):
        self.update_data()

    def update_data(self):
        current_lang = os.environ.get("DIALOGMESH_LANG", "en")
        lang_name = "English" if current_lang == "en" else "Chinese" if current_lang == "zh" else current_lang

        lines = []
        lines.append(t("tui.settings.title"))
        lines.append("=" * 50)
        lines.append("")
        lines.append(f"  [cyan]Data Source Mode: {self.ds.mode.upper()}[/]")
        lines.append(f"  API URL: {self.ds._api_url}")
        lines.append("")
        lines.append(t("tui.settings.lang", lang=current_lang, name=lang_name))
        lines.append("")
        lines.append(t("tui.settings.press"))
        lines.append(t("tui.settings.changed"))
        lines.append("")
        lines.append("  [dim]Shortcuts:[/]")
        lines.append("    r        Refresh all panels")
        lines.append("    1-9      Switch tabs")
        lines.append("    e/z      Language EN/ZH")
        lines.append("    F10/q    Quit")
        self.update("\n".join(lines))


# ═══════════════════════════════════════════════════════════════
# Main App
# ═══════════════════════════════════════════════════════════════

class DialogMeshTUI(App):
    """DialogMesh v4 Terminal Dashboard — Dual-mode (API + Offline)."""

    CSS = """
    Screen { align: center middle; }
    DataTable { height: 1fr; }
    Static { height: 1fr; padding: 1; }
    """

    TITLE = "DialogMesh v4 — Terminal Dashboard"
    SUB_TITLE = "Dual-mode: API + Offline"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ds = DataSource()
        self._tick = 0
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane(t("tui.dashboard.title"), id="dash"):
                yield DashboardTab(self.ds, id="dash-content")
            with TabPane(t("tui.observations.title"), id="obs"):
                yield ObservationsTab(self.ds, id="obs-content")
            with TabPane(t("tui.hypotheses.title"), id="hyp"):
                yield HypothesesTab(self.ds, id="hyp-content")
            with TabPane(t("tui.knowledge.title"), id="know"):
                yield KnowledgeTab(self.ds, id="know-content")
            with TabPane(t("tui.skills.title"), id="skill"):
                yield SkillsTab(self.ds, id="skill-content")
            with TabPane(t("tui.world.title"), id="world"):
                yield WorldTab(self.ds, id="world-content")
            with TabPane(t("tui.context.title"), id="ctx"):
                yield ContextTab(self.ds, id="ctx-content")
            with TabPane(t("tui.events.title"), id="evtlog"):
                yield EventLogTab(self.ds, id="evtlog-content")
            with TabPane(t("tui.settings.title"), id="settings"):
                yield SettingsTab(self.ds, id="settings-content")
        yield Footer()

    def on_mount(self):
        # Auto-start engine in background if offline mode
        if self.ds.mode == "none":
            self._start_engine_background()

        # Staggered refresh
        self._tick = 0
        self._timer = self.set_interval(1, self._staggered_refresh)
        self.notify(f"Mode: {self.ds.mode.upper()}", title="Data Source")

    def _start_engine_background(self):
        """Try to start engine in background thread."""
        import threading
        def _start():
            try:
                from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
                import core.agent.v4.cli.main as cm
                if cm._engine is None:
                    cm._engine = CognitiveRuntimeEngine()
                    cm._engine.start()
                    self.ds.refresh_mode()
                    self.notify("Engine started (offline mode)", title="Runtime")
            except Exception as e:
                self.notify(f"Engine: {e}", title="Runtime", severity="warning")
        t = threading.Thread(target=_start, daemon=True)
        t.start()

    def _staggered_refresh(self):
        """Staggered panel refresh to avoid UI freeze."""
        self._tick += 1

        # Always refresh Dashboard
        dash = self.query_one("#dash-content", DashboardTab)
        if dash:
            dash.update_stats()

        # Tick 2: Observations + Context
        if self._tick == 2:
            self._refresh_tab("#obs-content", ObservationsTab)
            self._refresh_tab("#ctx-content", ContextTab)

        # Tick 4: Hypotheses + Knowledge
        elif self._tick == 4:
            self._refresh_tab("#hyp-content", HypothesesTab)
            self._refresh_tab("#know-content", KnowledgeTab)

        # Tick 6: Skills + World
        elif self._tick == 6:
            self._refresh_tab("#skill-content", SkillsTab)
            self._refresh_tab("#world-content", WorldTab)

        # Tick 8+: All panels
        elif self._tick >= 8:
            self._refresh_tab("#obs-content", ObservationsTab)
            self._refresh_tab("#ctx-content", ContextTab)
            self._refresh_tab("#hyp-content", HypothesesTab)
            self._refresh_tab("#know-content", KnowledgeTab)
            self._refresh_tab("#skill-content", SkillsTab)
            self._refresh_tab("#world-content", WorldTab)

        # Always refresh Event Log + Settings
        self._refresh_tab("#evtlog-content", EventLogTab)
        self._refresh_tab("#settings-content", SettingsTab)

    def _refresh_tab(self, selector: str, tab_class):
        """Safely refresh a tab by selector."""
        try:
            tab = self.query_one(selector, tab_class)
            if tab and hasattr(tab, 'update_data'):
                tab.update_data()
        except Exception:
            pass

    def refresh_all(self):
        """Manual refresh all panels."""
        self.ds.refresh_mode()
        for selector, cls in [
            ("#dash-content", DashboardTab),
            ("#obs-content", ObservationsTab),
            ("#hyp-content", HypothesesTab),
            ("#know-content", KnowledgeTab),
            ("#skill-content", SkillsTab),
            ("#world-content", WorldTab),
            ("#ctx-content", ContextTab),
            ("#evtlog-content", EventLogTab),
            ("#settings-content", SettingsTab),
        ]:
            self._refresh_tab(selector, cls)
        self.notify("All panels refreshed", title="Refresh")

    def on_key(self, event):
        """Keyboard shortcuts."""
        # Language switching
        if event.key == "e":
            os.environ["DIALOGMESH_LANG"] = "en"
            from i18n import clear_cache
            clear_cache()
            self.notify("Language: English", title="Settings")
            self.refresh_all()
        elif event.key == "z":
            os.environ["DIALOGMESH_LANG"] = "zh"
            from i18n import clear_cache
            clear_cache()
            self.notify("Language: Chinese / 中文", title="Settings")
            self.refresh_all()
        # Refresh
        elif event.key == "r":
            self.refresh_all()
        # Tab switching (1-9)
        elif event.key in "123456789":
            idx = int(event.key) - 1
            tabs = self.query_one(TabbedContent)
            children = list(tabs.children)
            if idx < len(children):
                tabs.active = children[idx].id

    def on_unmount(self):
        """Cleanup."""
        try:
            import core.agent.v4.cli.main as cm
            if cm._engine:
                cm._engine.stop()
        except Exception:
            pass


def main():
    app = DialogMeshTUI()
    app.run()


if __name__ == "__main__":
    main()
