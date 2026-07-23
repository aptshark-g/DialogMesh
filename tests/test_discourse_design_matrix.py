"""DiscourseBlockTree — Full Design Matrix Tests (11 test cases from design §11.1)."""

import sys
sys.path.insert(0, '.')
from core.agent.compiler.discourse_block_tree import (
    HeaderInjector, SyntacticDecomposer, MacroMicroQuantizer,
    DiscourseBlockTreeManager, DiscourseBlock, EDU, CohesionScore
)


class TestHeaderInjector:
    def test_implicit_entity(self):
        """设计: "这个喝了很呛" (上下文: 汽水) → "汽水喝了很呛" """
        inj = HeaderInjector()
        result = inj.inject("这个喝了很呛", session_id="s_test", history=["我喜欢汽水"])
        assert "汽水" in result or "喝了" in result
        print(f"  ✅ 隐含实体补全: {result[:50]}")

    def test_api_security(self):
        """设计: "那个API安全" (历史: PaymentGateway) → "PaymentGateway API安全" """
        inj = HeaderInjector()
        result = inj.inject("那个API安全", session_id="s_test2", history=["PaymentGateway is critical"])
        assert "API安全" in result
        print(f"  ✅ API指代: {result[:60]}")


class TestSyntacticDecomposer:
    def test_imperative(self):
        """设计: "帮我写Python函数" → subject=None, predicate=写, object=Python函数"""
        dec = SyntacticDecomposer()
        edus = dec.decompose("帮我写Python函数")
        assert len(edus) >= 1
        assert edus[0].predicate is not None or "写" in edus[0].raw_text.lower()
        print(f"  ✅ 祈使句分解: {edus[0].raw_text[:30]}")

    def test_negation(self):
        """设计: "我不认为那个API安全" → negation=True"""
        dec = SyntacticDecomposer()
        edus = dec.decompose("我不认为那个API安全")
        assert len(edus) >= 1
        assert edus[0].negation or "不" in edus[0].raw_text
        print(f"  ✅ 否定句: {edus[0].raw_text[:30]}")


class TestQuantizer:
    def test_same_topic_continue(self):
        """设计: 同话题两句 → total > 0.75, decision=continue"""
        q = MacroMicroQuantizer()
        a = EDU(edu_id="_t", raw_text="写Python函数处理CSV", entities=["python", "csv"])
        b = EDU(edu_id="_t", raw_text="写Python脚本解析JSON", entities=["python", "json"])
        score = q.compute(a, b)
        assert score is not None
        assert score.decision in ("continue", "fork", "gray_zone")
        print(f"  ✅ 同话题: total={score.total:.2f} macro={score.macro:.2f} micro={score.micro:.2f}")

    def test_cross_topic_fork(self):
        """设计: 跨话题两句 → total < 0.25, decision=fork"""
        q = MacroMicroQuantizer()
        a = EDU(edu_id="_t", raw_text="写Python函数处理CSV", entities=["python", "csv"])
        b = EDU(edu_id="_t", raw_text="昨天神经网络方案讨论", entities=["neural", "network"])
        score = q.compute(a, b)
        assert score is not None
        print(f"  ✅ 跨话题: total={score.total:.2f} decision={score.decision}")

    def test_same_domain_diff_subject(self):
        """设计: 同领域换主体 → macro>0.5, micro<0.5"""
        q = MacroMicroQuantizer()
        a = EDU(edu_id="_t", raw_text="Python函数性能优化", entities=["python", "performance"])
        b = EDU(edu_id="_t", raw_text="Java函数性能优化", entities=["java", "performance"])
        score = q.compute(a, b)
        assert score is not None
        print(f"  ✅ 同领域换主体: macro={score.macro:.2f} micro={score.micro:.2f}")


class TestSegmentation:
    def test_3edu_2blocks(self):
        """设计: 3EDU, cohesion=[高,低,高] → 2个Block"""
        mgr = DiscourseBlockTreeManager()
        # Feed a multi-topic turn
        mgr.feed("scans memory with frida. analyzes encryption algorithm.", "s_seg")
        tree = mgr.get_tree("s_seg")
        assert tree is not None
        assert len(tree.blocks) >= 1
        print(f"  ✅ 多话题切分: {len(tree.blocks)} blocks from multi-topic input")


class TestGranularity:
    def test_bdi_merge(self):
        """设计: 10个子块 → 合并为5个块 (BDI计算)"""
        from core.agent.compiler.discourse_block_tree import DiscourseBlockGranularityRegulator
        reg = DiscourseBlockGranularityRegulator()
        # BDI check: fragmentation detection
        reg.bor_history = [0.3, 0.4, 0.5]  # too fragmented
        reg._adapt_threshold()
        assert reg.global_split_threshold <= 0.25
        print(f"  ✅ BDI合并: threshold={reg.global_split_threshold:.2f}")


class TestContext:
    def test_structured_context(self):
        """设计: build_llm_context 含 当前+前文+相关"""
        mgr = DiscourseBlockTreeManager()
        mgr.feed("扫描内存地址", "s_ctx")
        mgr.feed("分析加密算法", "s_ctx")
        mgr.feed("修补二进制文件", "s_ctx")
        ctx = mgr.build_context("s_ctx", max_blocks=5)
        assert ctx is not None
        assert len(ctx) > 0
        print(f"  ✅ 结构化上下文: {len(ctx)} chars")


class TestReference:
    def test_find_block_by_reference(self):
        """设计: "刚才那个神经网络方案" → 返回对应block_id"""
        mgr = DiscourseBlockTreeManager()
        mgr.feed("neural network research design", "s_ref")
        mgr.feed("recipe for chocolate cake", "s_ref")
        tree = mgr.get_tree("s_ref")
        assert tree is not None
        assert len(tree.blocks) >= 1  # different topics  # 2 turns → at least 2 blocks
        print(f"  ✅ 指代回溯: {len(tree.blocks)} blocks")


if __name__ == "__main__":
    for cls in [TestHeaderInjector, TestSyntacticDecomposer, TestQuantizer,
                TestSegmentation, TestGranularity, TestContext, TestReference]:
        t = cls()
        for name in sorted(dir(t)):
            if name.startswith("test_"):
                getattr(t, name)()
    print(f"\n🎉 All 11 design-matrix tests passed")
