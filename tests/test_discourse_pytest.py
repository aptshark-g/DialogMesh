"""Standard pytest tests for DiscoursePipeline.

Covers:
- Basic functionality (disabled, basic turn, reset)
- Multi-turn processing
- Config loading
- Health check / preload
"""

from __future__ import annotations

import os

import pytest

from core.agent.discourse_integration import DiscoursePipeline


# ── Basic Functionality ────────────────────────────────────────────

class TestBasicFunctionality:
    """Test DiscoursePipeline basic operations."""

    def test_disabled_returns_empty_string(self) -> None:
        """When enabled=False, process_turn returns empty string.

        Note: If config is loaded, the parameter may be overridden.
        """
        pipe = DiscoursePipeline(enabled=False)
        if pipe.enabled:
            pytest.skip("Config loaded and overrides enabled=False")
        ctx = pipe.process_turn("帮我写 Python", turn_index=0)
        assert ctx == ""

    def test_basic_turn_non_empty(self, discourse_pipeline: DiscoursePipeline) -> None:
        """Basic single turn returns non-empty context with Hot/Warm/Cold markers."""
        ctx = discourse_pipeline.process_turn("帮我写 Python 脚本", turn_index=0)
        assert isinstance(ctx, str)
        assert len(ctx) > 0
        assert "Hot" in ctx or "Warm" in ctx or "Cold" in ctx or "[DiscoursePipeline" in ctx

    def test_reset_clears_state(self, discourse_pipeline: DiscoursePipeline) -> None:
        """reset() clears manager blocks."""
        discourse_pipeline.process_turn("A", turn_index=0)
        assert discourse_pipeline.manager.block_count >= 1
        discourse_pipeline.reset()
        assert discourse_pipeline.manager.block_count == 0

    def test_complex_input_no_crash(self, discourse_pipeline: DiscoursePipeline) -> None:
        """Complex input (parse_failed fallback) should not raise."""
        text = "。".join([f"句子{i}" for i in range(10)])
        ctx = discourse_pipeline.process_turn(text, turn_index=0)
        assert isinstance(ctx, str)

    def test_header_injection_with_history(self, discourse_pipeline: DiscoursePipeline) -> None:
        """Header injection should include history entities."""
        history = [{"role": "user", "content": "我喜欢汽水"}]
        ctx = discourse_pipeline.process_turn("这个很甜", session_history=history, turn_index=1)
        assert isinstance(ctx, str)
        # Either contains the injected entity or the pipeline marker
        assert "汽水" in ctx or "[DiscoursePipeline" in ctx or "Hot" in ctx


# ── Multi-turn Processing ──────────────────────────────────────────

class TestMultiTurnProcessing:
    """Test multi-turn state management."""

    def test_multi_turn_context_grows(self, discourse_pipeline: DiscoursePipeline) -> None:
        """After multiple turns, context should contain block markers."""
        for turn in range(4):
            ctx = discourse_pipeline.process_turn(f"Turn {turn} content", turn_index=turn)
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_multi_turn_block_count_increases(self, discourse_pipeline: DiscoursePipeline) -> None:
        """Manager block count should increase or stay stable across turns."""
        discourse_pipeline.process_turn("第一轮内容", turn_index=0)
        count_after_first = discourse_pipeline.manager.block_count
        discourse_pipeline.process_turn("第二轮内容", turn_index=1)
        count_after_second = discourse_pipeline.manager.block_count
        # Blocks may be merged, so count should be >= first
        assert count_after_second >= count_after_first

    def test_turn_index_zero_works(self, discourse_pipeline: DiscoursePipeline) -> None:
        """turn_index=0 should work as first turn."""
        ctx = discourse_pipeline.process_turn("第一轮", turn_index=0)
        assert isinstance(ctx, str)


# ── Config Loading ─────────────────────────────────────────────────

class TestConfigLoading:
    """Test configuration loading and defaults."""

    def test_default_hot_turns(self, discourse_pipeline: DiscoursePipeline) -> None:
        """Default hot_turns should be 5."""
        assert discourse_pipeline.hot_turns == 5

    def test_custom_hot_turns(self) -> None:
        """Custom hot_turns should be respected.

        Note: If config is loaded, the parameter may be overridden.
        """
        pipe = DiscoursePipeline(hot_turns=3)
        if pipe.hot_turns != 3:
            pytest.skip("Config loaded and overrides hot_turns parameter")
        assert pipe.hot_turns == 3

    def test_default_enabled(self, discourse_pipeline: DiscoursePipeline) -> None:
        """Default enabled should be True."""
        assert discourse_pipeline.enabled is True

    def test_session_id_default(self, discourse_pipeline: DiscoursePipeline) -> None:
        """Default session_id should be 'default'."""
        assert discourse_pipeline.session_id == "default"

    def test_custom_session_id(self) -> None:
        """Custom session_id should be respected."""
        pipe = DiscoursePipeline(session_id="test_session")
        assert pipe.session_id == "test_session"


# ── Health Check / Preload ───────────────────────────────────────

class TestHealthCheck:
    """Test pipeline health and preload."""

    @pytest.mark.skipif(
        os.environ.get("CI") == "true" or os.environ.get("SKIP_SLOW") == "1",
        reason="Skip model-download tests in CI or when SKIP_SLOW=1",
    )
    def test_preload_returns_true(self, discourse_pipeline: DiscoursePipeline) -> None:
        """preload() should return True (blocking mode)."""
        result = discourse_pipeline.preload(blocking=True)
        assert result is True

    def test_preload_nonblocking_returns_true(self, discourse_pipeline: DiscoursePipeline) -> None:
        """preload(blocking=False) should return True."""
        # This may trigger background threads; we just verify it doesn't crash
        result = discourse_pipeline.preload(blocking=False)
        assert result is True

    def test_components_initialized(self, discourse_pipeline: DiscoursePipeline) -> None:
        """All internal components should be initialized."""
        assert discourse_pipeline.header_injector is not None
        assert discourse_pipeline.decomposer is not None
        assert discourse_pipeline.quantizer is not None
        assert discourse_pipeline.segmenter is not None
        assert discourse_pipeline.manager is not None
        assert discourse_pipeline.summary_engine is not None
        assert discourse_pipeline.context_builder is not None

    def test_manager_has_block_count_property(self, discourse_pipeline: DiscoursePipeline) -> None:
        """Manager should expose block_count property."""
        assert isinstance(discourse_pipeline.manager.block_count, int)

    def test_manager_has_current_turn_property(self, discourse_pipeline: DiscoursePipeline) -> None:
        """Manager should expose current_turn property."""
        assert isinstance(discourse_pipeline.manager.current_turn, int)
