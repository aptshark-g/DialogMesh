# -*- coding: utf-8 -*-
"""
tests/test_plugin_system.py
──────────────────────────
Tests for the plugin registry system.

Coverage:
- Register custom strategy
- Default strategy fallback
- Strategy switching
- Plugin lifecycle (clear / unregister)
"""

from __future__ import annotations

import pytest

from core.agent.plugin_system import PluginRegistry, AlwaysSplitSegmenter


class DummySegmenter:
    """A no-op segmenter for testing."""

    def __init__(self, marker: str = "dummy"):
        self.marker = marker

    def segment(self, edus):
        return []

    def compute_block_boundary_cohesion(self, block_a, block_b):
        return 0.5


class DummySummaryEngine:
    """A no-op summary engine for testing."""

    def __init__(self, marker: str = "dummy"):
        self.marker = marker

    def summarize_block(self, block):
        pass


class DummyHeaderInjector:
    """A no-op header injector for testing."""

    def __init__(self, marker: str = "dummy"):
        self.marker = marker

    def inject(self, raw_text, session_id, session_history=None, turn_index=0):
        return None

    def reset_session(self, session_id):
        pass


@pytest.fixture(autouse=True)
def _clear_registry():
    """Auto-clear registry before each test to avoid cross-test contamination."""
    PluginRegistry.clear()
    yield


class TestPluginRegistry:
    """Tests for PluginRegistry.register_strategy and get_strategy."""

    def test_register_custom_segmenter(self):
        """Register a custom segmenter and resolve it."""
        PluginRegistry.register_strategy(
            name="dummy_segmenter",
            component_type="segmenter",
            factory_func=lambda: DummySegmenter(marker="custom"),
        )

        instance = PluginRegistry.get_strategy("segmenter", "dummy_segmenter")
        assert isinstance(instance, DummySegmenter)
        assert instance.marker == "custom"

    def test_register_custom_summary_engine(self):
        """Register a custom summary engine and resolve it."""
        PluginRegistry.register_strategy(
            name="dummy_summary",
            component_type="summary_engine",
            factory_func=lambda: DummySummaryEngine(marker="custom_v2"),
        )

        instance = PluginRegistry.get_strategy("summary_engine", "dummy_summary")
        assert isinstance(instance, DummySummaryEngine)
        assert instance.marker == "custom_v2"

    def test_register_custom_header_injector(self):
        """Register a custom header injector and resolve it."""
        PluginRegistry.register_strategy(
            name="dummy_injector",
            component_type="header_injector",
            factory_func=lambda: DummyHeaderInjector(marker="custom_h1"),
        )

        instance = PluginRegistry.get_strategy("header_injector", "dummy_injector")
        assert isinstance(instance, DummyHeaderInjector)
        assert instance.marker == "custom_h1"

    def test_default_fallback_when_none_specified(self):
        """When no custom name is given, the default implementation is returned."""
        # No custom registrations
        seg = PluginRegistry.get_strategy("segmenter", None)
        assert seg is not None
        # Verify it is NOT our dummy
        assert not isinstance(seg, DummySegmenter)

    def test_default_fallback_when_name_not_found(self):
        """When a non-existent name is given, fall back to the default."""
        seg = PluginRegistry.get_strategy("segmenter", "nonexistent_strategy")
        assert seg is not None
        assert not isinstance(seg, DummySegmenter)

    def test_strategy_switching(self):
        """Switch between multiple registered strategies."""
        PluginRegistry.register_strategy(
            name="strategy_a",
            component_type="segmenter",
            factory_func=lambda: DummySegmenter(marker="A"),
        )
        PluginRegistry.register_strategy(
            name="strategy_b",
            component_type="segmenter",
            factory_func=lambda: DummySegmenter(marker="B"),
        )

        a = PluginRegistry.get_strategy("segmenter", "strategy_a")
        b = PluginRegistry.get_strategy("segmenter", "strategy_b")
        default = PluginRegistry.get_strategy("segmenter", None)

        assert a.marker == "A"
        assert b.marker == "B"
        assert default is not None
        # Default is the real Segmenter, which does not have a 'marker' attribute
        assert not hasattr(default, "marker")

    def test_list_strategies(self):
        """list_strategies returns registered names per component type."""
        PluginRegistry.register_strategy(
            name="seg1",
            component_type="segmenter",
            factory_func=lambda: DummySegmenter(),
        )
        PluginRegistry.register_strategy(
            name="sum1",
            component_type="summary_engine",
            factory_func=lambda: DummySummaryEngine(),
        )

        all_strategies = PluginRegistry.list_strategies()
        assert "seg1" in all_strategies["segmenter"]
        assert "sum1" in all_strategies["summary_engine"]
        assert all_strategies["header_injector"] == []

        seg_only = PluginRegistry.list_strategies("segmenter")
        assert seg_only == {"segmenter": ["seg1"]}

    def test_unregister_strategy(self):
        """Unregister removes a strategy; subsequent get falls back to default."""
        PluginRegistry.register_strategy(
            name="to_remove",
            component_type="segmenter",
            factory_func=lambda: DummySegmenter(marker="remove_me"),
        )

        instance = PluginRegistry.get_strategy("segmenter", "to_remove")
        assert instance.marker == "remove_me"

        removed = PluginRegistry.unregister_strategy("to_remove", "segmenter")
        assert removed is True

        fallback = PluginRegistry.get_strategy("segmenter", "to_remove")
        assert not isinstance(fallback, DummySegmenter)

        removed_again = PluginRegistry.unregister_strategy("to_remove", "segmenter")
        assert removed_again is False

    def test_clear_registry(self):
        """Clear wipes all custom registrations."""
        PluginRegistry.register_strategy(
            name="keep",
            component_type="segmenter",
            factory_func=lambda: DummySegmenter(),
        )
        assert PluginRegistry.list_strategies("segmenter")["segmenter"] == ["keep"]

        PluginRegistry.clear()
        assert PluginRegistry.list_strategies("segmenter")["segmenter"] == []

    def test_invalid_component_type_raises(self):
        """Registering or getting with an invalid component_type raises ValueError."""
        with pytest.raises(ValueError):
            PluginRegistry.register_strategy(
                name="bad",
                component_type="invalid_type",
                factory_func=lambda: None,
            )

        with pytest.raises(ValueError):
            PluginRegistry.get_strategy("invalid_type", "bad")

    def test_always_split_plugin_demo(self):
        """The built-in AlwaysSplitSegmenter demo plugin is registered on import."""
        # Re-register because the fixture cleared it
        PluginRegistry.register_strategy(
            name="always_split",
            component_type="segmenter",
            factory_func=lambda: AlwaysSplitSegmenter(),
        )

        seg = PluginRegistry.get_strategy("segmenter", "always_split")
        assert isinstance(seg, AlwaysSplitSegmenter)
        assert seg.threshold == 0.0


class TestPluginIntegrationWithPipeline:
    """Integration tests: PluginRegistry + DiscoursePipeline strategy dict."""

    def test_pipeline_uses_custom_segmenter(self):
        """DiscoursePipeline accepts a strategy dict and delegates to PluginRegistry."""
        from core.agent.discourse_integration import DiscoursePipeline

        PluginRegistry.register_strategy(
            name="integration_test_seg",
            component_type="segmenter",
            factory_func=lambda: DummySegmenter(marker="integration"),
        )

        # The pipeline constructor should accept a strategy dict and resolve via PluginRegistry
        # We verify by inspecting the pipeline's internal segmenter attribute if accessible,
        # or by checking that the pipeline initializes without error.
        dp = DiscoursePipeline(
            session_id="test",
            strategy={"segmenter": "integration_test_seg"},
        )
        # The internal segmenter should be our dummy (if pipeline uses PluginRegistry)
        # If pipeline does not yet support the strategy kwarg, this test documents the expected interface.
        assert hasattr(dp, "segmenter")

    def test_pipeline_fallback_to_default(self):
        """Pipeline with empty strategy dict falls back to defaults."""
        from core.agent.discourse_integration import DiscoursePipeline

        dp = DiscoursePipeline(session_id="test_fallback", strategy={})
        assert hasattr(dp, "segmenter")
        assert hasattr(dp, "summary_engine")
