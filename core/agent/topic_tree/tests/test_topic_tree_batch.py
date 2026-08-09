# -*- coding: utf-8 -*-
"""
主题树 T1-T7 批次测试（2026-08-05）。

覆盖:
  T1  EmbeddingEngine 宽异常兜底（非 ImportError 环境问题回退 hash）
  T2  get_current_branch 真实现（context_assembly 断点修复）
  T3  get_active_path 别名 + engineering TopicTreeBridge 真数据
  T4  V1/V2 归一（门面 = V2 内核 + 归档 + registry 指向）
  T5  阈值参数化（config 覆盖 + 分类器/分叉定位器参数）
  T6  激活策略（auto_activate 首轮建树 / 可关闭）
  T7  编码器契约（register_encoder / 身份标记 / 跨空间语义置 0）
"""

import builtins
import unittest

from core.agent.topic_tree.manager_v2 import (
    EmbeddingEngine,
    TopicTreeManagerV2,
    TopicDecisionClassifier,
    CohesionCalculator,
    DEFAULT_TOPIC_TREE_CONFIG,
)
from core.agent.topic_tree.models import TopicNode


def _reset_encoder():
    EmbeddingEngine.reset()


class TestT1_EmbeddingRobustness(unittest.TestCase):
    """T1: 模型加载任何异常都回退 hash，绝不抛。"""

    def test_broken_import_chain_falls_back(self):
        """模拟环境导入链抛 ValueError（huggingface_hub 版本检查崩溃）→ hash 兜底。"""
        orig_import = builtins.__import__

        def broken_import(name, *args, **kwargs):
            if name.startswith("sentence_transformers"):
                raise ValueError("simulated broken import chain")
            return orig_import(name, *args, **kwargs)

        EmbeddingEngine._model = None
        builtins.__import__ = broken_import
        try:
            vec = EmbeddingEngine.encode("test query")
            self.assertIsInstance(vec, list)
            self.assertEqual(len(vec), 384)
            self.assertEqual(EmbeddingEngine.current_encoder(), "hash")
        finally:
            builtins.__import__ = orig_import
            _reset_encoder()

    def test_model_encode_failure_falls_back(self):
        """编码阶段异常同样回退 hash。"""
        class _FakeModel:
            def encode(self, text, normalize_embeddings=True):
                raise RuntimeError("model runtime failure")

        orig_load = EmbeddingEngine._load_model
        EmbeddingEngine._load_model = classmethod(lambda cls: _FakeModel())
        try:
            vec = EmbeddingEngine.encode("x")
            self.assertEqual(len(vec), 384)
        finally:
            EmbeddingEngine._load_model = orig_load
            _reset_encoder()


class TestT2_T3_BranchAPI(unittest.TestCase):
    """T2/T3: get_current_branch / get_active_path 真实现。"""

    def setUp(self):
        _reset_encoder()
        self.mgr = TopicTreeManagerV2()
        self.mgr.activate([])

    def tearDown(self):
        _reset_encoder()

    def test_current_branch_root_to_current(self):
        """continue 后分支只有根节点；fork 后分支含父+子。"""
        self.mgr.route("hello", 1, query_intent="ADVISOR")
        branch = self.mgr.get_current_branch()
        self.assertEqual(len(branch), 1)
        self.assertEqual(branch[0].name, "hello")

    def test_current_branch_empty_when_no_tree(self):
        empty = TopicTreeManagerV2()
        self.assertEqual(empty.get_current_branch(), [])
        self.assertEqual(empty.get_active_path(), [])

    def test_active_path_alias(self):
        """get_active_path = get_current_branch（engineering TopicTreeBridge 消费方）。"""
        self.mgr.route("a", 1, query_intent="ADVISOR")
        self.mgr.route("b", 2, query_intent="DIRECTIVE")
        # 意图漂移 → fork：分支 = root(a) → b
        path = self.mgr.get_active_path()
        self.assertGreaterEqual(len(path), 2)
        self.assertEqual(path[-1].name, "b")
        self.assertEqual([n.id for n in path], [n.id for n in self.mgr.get_current_branch()])

    def test_context_assembly_gets_real_branch(self):
        """T2 消费方: ContextAssembly._gather_sources 不再恒空。"""
        from core.agent.assembly.context_assembly import ContextAssembly
        tt = TopicTreeManagerV2()
        tt.activate([])
        tt.route("hello", 1, query_intent="COMPANION")
        ca = ContextAssembly(topic_tree_manager=tt)
        gathered = ca._gather_sources({})
        self.assertIn("topic_tree", gathered)
        self.assertEqual(len(gathered["topic_tree"]), 1)
        self.assertIsInstance(gathered["topic_tree"][0], dict)

    def test_engineering_bridge_real_data(self):
        """T3 消费方: TopicTreeBridge.get_current_branch 不再恒 []。"""
        from core.agent.engineering_bridges import TopicTreeBridge
        bridge = TopicTreeBridge()
        self.assertEqual(bridge.get_current_branch(), [])  # 未激活无树
        bridge._ensure()
        bridge._tree.activate([])
        bridge._tree.route("hello", 1, query_intent="COMPANION")
        branch = bridge.get_current_branch()
        self.assertEqual(len(branch), 1)
        summary = bridge.get_summary()
        self.assertIn("total_nodes", summary)
        self.assertEqual(summary["total_nodes"], 1)


class TestT4_V1V2Normalization(unittest.TestCase):
    """T4: V1/V2 归一 — 门面 = V2 内核，组件资产保留。"""

    def test_facade_points_to_v2_kernel(self):
        from core.agent.topic_tree import TopicTreeManager, TopicTreeManagerV2, RoutingDecision
        from core.agent.topic_tree.manager import TopicTreeManager as FacadeManager
        self.assertIs(TopicTreeManager, TopicTreeManagerV2)
        self.assertIs(FacadeManager, TopicTreeManagerV2)
        self.assertEqual(RoutingDecision.__name__, "RoutingDecisionV2")

    def test_v1_archived_not_imported(self):
        """V1 原始包装类已归档 un_use，主路径不再引用。"""
        import os
        archive = os.path.join(os.path.dirname(__file__), "..", "un_use", "manager_v1.py")
        self.assertTrue(os.path.exists(archive))
        # 主模块不依赖 V1 类
        import core.agent.topic_tree as tt_pkg
        self.assertNotIn("manager_v1", str(tt_pkg.__file__))

    def test_registry_points_to_v2(self):
        """CLI registry 注册串指向 V2 内核（T4 归一）。"""
        from core.agent.cli.registry import build_dialogmesh_registry
        from core.agent.cli.subsystem_registrations import _registry
        reg = build_dialogmesh_registry()
        self.assertEqual(reg._defs["topic_tree"].path, "core.agent.topic_tree.manager_v2:TopicTreeManagerV2")
        self.assertEqual(_registry._defs["topic_tree"].path, "core.agent.topic_tree.manager_v2:TopicTreeManagerV2")

    def test_component_assets_still_exported(self):
        from core.agent.topic_tree import (
            AdaptiveHeatModel, FactStore, DualPerspectiveContext,
        )
        self.assertTrue(callable(AdaptiveHeatModel))
        self.assertTrue(callable(FactStore))
        self.assertTrue(callable(DualPerspectiveContext))


class TestT5_ThresholdParameterization(unittest.TestCase):
    """T5: 阈值/权重全部参数化（A18 参数自适应入口）。"""

    def setUp(self):
        _reset_encoder()

    def tearDown(self):
        _reset_encoder()

    def test_default_config_matches_previous_hardcode(self):
        mgr = TopicTreeManagerV2()
        self.assertEqual(mgr.cohesion_continue, 0.55)
        self.assertEqual(mgr.cohesion_fork, 0.25)
        self.assertEqual(mgr.max_depth, 6)
        self.assertEqual(mgr.hot_zone_depth, 2)
        self.assertEqual(mgr.activation_threshold, 10)
        # 分类器/分叉定位器接收默认参数
        self.assertEqual(mgr.decision_classifier.intent_drift_threshold, 0.3)
        self.assertEqual(mgr.decision_classifier.merge_similarity, 0.85)
        self.assertEqual(mgr.fork_locator.similarity_threshold, 0.4)

    def test_config_override(self):
        mgr = TopicTreeManagerV2(config={
            "max_depth": 3,
            "hot_zone_depth": 1,
            "activation_threshold": 5,
            "cohesion_continue": 0.7,
            "merge_similarity": 0.9,
            "fork_similarity_threshold": 0.6,
        })
        self.assertEqual(mgr.max_depth, 3)
        self.assertEqual(mgr.hot_zone_depth, 1)
        self.assertEqual(mgr.activation_threshold, 5)
        self.assertEqual(mgr.cohesion_continue, 0.7)
        self.assertEqual(mgr.decision_classifier.merge_similarity, 0.9)
        self.assertEqual(mgr.fork_locator.similarity_threshold, 0.6)
        self.assertFalse(mgr.should_activate(4))
        self.assertTrue(mgr.should_activate(5))

    def test_classifier_standalone_params(self):
        clf = TopicDecisionClassifier(intent_drift_threshold=0.5, merge_similarity=0.9)
        self.assertEqual(clf.intent_drift_threshold, 0.5)
        self.assertEqual(clf.merge_similarity, 0.9)

    def test_intent_related_configurable(self):
        """T5: 意图映射表可配置（CohesionCalculator 实例级）。"""
        calc = CohesionCalculator(intent_related={("A", "B"): 0.99})
        self.assertAlmostEqual(calc._intent_consistency("A", "B"), 0.99)
        self.assertEqual(calc._intent_consistency("ADVISOR", "QUERY"), 0.0)  # 默认映射被替换

    def test_all_thresholds_in_default_config(self):
        """T5: 每个默认阈值都在 DEFAULT_TOPIC_TREE_CONFIG 中可覆盖。"""
        self.assertIn("cohesion_continue", DEFAULT_TOPIC_TREE_CONFIG)
        self.assertIn("max_depth", DEFAULT_TOPIC_TREE_CONFIG)
        self.assertIn("activation_threshold", DEFAULT_TOPIC_TREE_CONFIG)
        self.assertIn("merge_similarity", DEFAULT_TOPIC_TREE_CONFIG)
        self.assertIn("intent_drift_threshold", DEFAULT_TOPIC_TREE_CONFIG)


class TestT6_ActivationPolicy(unittest.TestCase):
    """T6: 激活策略 — 默认首轮建树，可关闭延迟策略。"""

    def setUp(self):
        _reset_encoder()

    def tearDown(self):
        _reset_encoder()

    def test_auto_activate_on_first_route(self):
        mgr = TopicTreeManagerV2()  # 未显式 activate
        result = mgr.route("hello", 1, query_intent="COMPANION")
        self.assertEqual(result.action, "new")
        self.assertTrue(mgr.is_active())

    def test_auto_activate_disabled(self):
        mgr = TopicTreeManagerV2(config={"auto_activate": False})
        result = mgr.route("hello", 1, query_intent="COMPANION")
        self.assertEqual(result.action, "continue")
        self.assertFalse(mgr.is_active())
        # should_activate 仍是外部策略入口
        self.assertFalse(mgr.should_activate(9))
        self.assertTrue(mgr.should_activate(10))


class TestT7_EncoderContract(unittest.TestCase):
    """T7: 编码器契约 — 注册/身份/维度/跨空间语义置 0。"""

    def setUp(self):
        _reset_encoder()

    def tearDown(self):
        _reset_encoder()

    def test_register_encoder_contract(self):
        EmbeddingEngine.register_encoder("fake_bge", lambda t: [0.5] * 512)
        self.assertEqual(EmbeddingEngine.current_encoder(), "fake_bge")
        self.assertTrue(EmbeddingEngine.supports_semantics())
        vec = EmbeddingEngine.encode("x")
        self.assertEqual(len(vec), 512)

    def test_hash_not_semantic_capable(self):
        self.assertEqual(EmbeddingEngine.current_encoder(), "hash")
        self.assertFalse(EmbeddingEngine.supports_semantics())

    def test_nodes_tagged_with_encoder(self):
        mgr = TopicTreeManagerV2()
        mgr.activate([])
        mgr.route("hello", 1, query_intent="COMPANION")
        node = mgr.get_current_node()
        self.assertEqual(node.metadata["embedding_encoder"], EmbeddingEngine.current_encoder())
        self.assertEqual(node.metadata["embedding_dim"], 384)

    def test_mismatched_encoder_semantic_zero(self):
        """跨空间比较（hash 节点 vs BGE 编码器）→ 语义贡献 0，实体/意图仍参与。"""
        EmbeddingEngine.register_encoder("bge_512", lambda t: [0.5] * 512)
        calc = CohesionCalculator()
        node = TopicNode(
            name="old",
            embedding=[0.1] * 384,
            metadata={"embedding_encoder": "hash", "embedding_dim": 384},
            intent_category="ADVISOR",
        )
        res = calc.calculate("q", [0.5] * 512, "ADVISOR", [], node)
        self.assertEqual(res.semantic, 0.0)
        self.assertEqual(res.intent, 1.0)

    def test_same_encoder_still_computes(self):
        calc = CohesionCalculator()
        emb = [1.0] + [0.0] * 383
        node = TopicNode(name="n", embedding=emb, intent_category="ADVISOR")
        res = calc.calculate("q", emb, "ADVISOR", [], node)
        self.assertGreater(res.semantic, 0.9)


if __name__ == "__main__":
    unittest.main()
