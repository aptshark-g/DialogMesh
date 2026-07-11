"""Tests for Projector."""
import pytest
from core.agent.v4.observation_compiler.projector import Projector


class TestProjector:
    def test_dialog_message_routes_to_dialogue(self):
        p = Projector()
        domains = p.project("dialog.message")
        assert "dialogue" in domains
        assert "memory" in domains

    def test_ui_drag_routes_to_engineering(self):
        p = Projector()
        domains = p.project("ui.drag")
        assert "engineering" in domains
        assert "behavior" in domains

    def test_unknown_kind_defaults_to_memory(self):
        p = Projector()
        domains = p.project("unknown.event")
        assert domains == ["memory"]

    def test_all_domains_returns_all(self):
        p = Projector()
        domains = p.all_domains()
        assert "engineering" in domains
        assert "dialogue" in domains
        assert "behavior" in domains
        assert "memory" in domains
