# pragma: no cover
import pytest, json, tempfile, os
from core.agent.v3_2.parameter_registry import (
    ParameterRegistry, REGISTRY, SignalSource, SignalEvent,
    ParameterSnapshot, v4ParamConfig, create_registry_with_preset
)

class TestParameterRegistry:
    def test_registry_creation(self):
        reg = ParameterRegistry()
        reg.register_preset()
        v = reg.value(f{quoted}compiler_confidence{quoted})
        assert v == 0.75

    def test_dot_notation_namespace(self):
        v = REGISTRY.value(f{quoted}compiler_confidence{quoted})
        assert v == 0.75

    def test_graph_alpha_default(self):
        assert REGISTRY.value(f{quoted}graph_alpha{quoted}) == 0.25

    def test_graph_beta_default(self):
        assert REGISTRY.value(f{quoted}graph_beta{quoted}) == 0.30

    def test_graph_gamma_default(self):
        assert REGISTRY.value(f{quoted}graph_gamma{quoted}) == 0.05

    def test_graph_delta_default(self):
        assert REGISTRY.value(f{quoted}graph_delta{quoted}) == 0.05

    def test_foa_decay_default(self):
        assert REGISTRY.value(f{quoted}foa_decay{quoted}) == 0.30

    def test_foa_threshold_default(self):
        assert REGISTRY.value(f{quoted}foa_threshold{quoted}) == 0.30

    def test_apply_signal_increases_value(self):
        reg = create_registry_with_preset()
        before = reg.value("graph_alpha")
        reg.apply_signal("graph_alpha", 0.05, source=SignalSource.REWARDER)
        after = reg.value("graph_alpha")
        assert after > before

    def test_apply_signal_decreases_value(self):
        reg = create_registry_with_preset()
        before = reg.value("graph_alpha")
        reg.apply_signal("graph_alpha", -0.05, source=SignalSource.REWARDER)
        after = reg.value("graph_alpha")
        assert after < before

    def test_signal_clamped_to_bounds(self):
        reg = create_registry_with_preset()
        for _ in range(50):
            reg.apply_signal("graph_alpha", 0.1, source=SignalSource.REWARDER)
        assert reg.value("graph_alpha") <= 0.40

    def test_switch_strategy_conservative(self):
        reg = create_registry_with_preset()
        reg.switch_strategy("conservative")
        assert reg._active_strategy == "conservative"

    def test_switch_strategy_aggressive(self):
        reg = create_registry_with_preset()
        reg.switch_strategy("aggressive")
        assert reg._active_strategy == "aggressive"

    def test_snapshot_and_drift(self):
        reg = create_registry_with_preset()
        snap = reg.snapshot("graph_alpha")
        assert isinstance(snap, ParameterSnapshot)
        assert snap.name == "graph_alpha"
        assert -1.0 <= snap.drift_from_anchor() <= 1.0

    def test_save_and_load(self):
        import tempfile, os
        reg = create_registry_with_preset()
        reg.apply_signal("graph_alpha", 0.05, source=SignalSource.REWARDER)
        path = os.path.join(tempfile.gettempdir(), "test_registry.json")
        try:
            reg.save(path)
            reg2 = ParameterRegistry()
            reg2.register_preset()
            reg2.load(path)
            assert reg2.value("graph_alpha") == reg.value("graph_alpha")
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_clone_for_context(self):
        reg = create_registry_with_preset()
        reg.apply_signal("graph_alpha", 0.05, source=SignalSource.REWARDER)
        clone = reg.clone_for_context()
        assert clone.value("graph_alpha") == reg.value("graph_alpha")
        clone.apply_signal("graph_alpha", 0.03, source=SignalSource.MANUAL)
        assert clone.value("graph_alpha") != reg.value("graph_alpha")

    def test_do_calculus_backdoor_default(self):
        assert REGISTRY.value("do_calculus_backdoor") == 0.95

    def test_consolidation_merge_default(self):
        assert REGISTRY.value("consolidation_merge") == 15

    def test_consolidation_delta_default(self):
        assert REGISTRY.value("consolidation_delta") == 0.0

    def test_embedding_behavior_default(self):
        assert REGISTRY.value("embedding_behavior") == 0.30

    def test_embedding_index_default(self):
        assert REGISTRY.value("embedding_index") == 0.20

    def test_persistence_save_default(self):
        assert REGISTRY.value("persistence_save") == 60

    def test_metacognition_token_default(self):
        assert REGISTRY.value("metacognition_token") == 10000