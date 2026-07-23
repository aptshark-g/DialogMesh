"""Discourse Block Tree 性能基准测试。

使用纯 timeit 模块（pytest-benchmark 未安装时回退），
测量核心编译器管道和话语块树的延迟与吞吐。

运行方式:
    C:/Users/APTShark/anaconda3/envs/MemoryGraph/python.exe -m pytest tests/benchmark/test_benchmark.py -v
    # 或纯 Python 运行（无需 pytest）:
    C:/Users/APTShark/anaconda3/envs/MemoryGraph/python.exe tests/benchmark/test_benchmark.py
"""

from __future__ import annotations

import os
import sys
import timeit
from typing import Callable, List, Tuple

import pytest

# ── 路径设置 ──────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

# ── 被测模块 ──────────────────────────────────────────────────────
from core.agent.discourse_integration import DiscoursePipeline
from core.agent.compiler.header_injector import HeaderInjector
from core.agent.discourse_block_tree.segmenter import Segmenter
from core.agent.discourse_block_tree.models import EDU, MacroDimensions, MicroDimensions
from core.agent.compiler.syntactic_decomposer import SyntacticDecomposer
from core.agent.compiler.macro_micro_quantizer import MacroMicroQuantizer

# ── 常量 ──────────────────────────────────────────────────────────
WARMUP_TEXT = "帮我写 Python 脚本，分析 Redis 内存数据"
BATCH_TEXTS = [
    "帮我写 Python 脚本",
    "分析 Redis 内存数据",
    "检查 Docker 容器状态",
    "推荐一个轻量数据库",
    "如何优化 C++ 性能",
    "TensorFlow 模型部署",
    "分析系统日志文件",
    "检查网络连接延迟",
    "推荐一个 Web 框架",
    "如何学习机器学习",
]

# ── 辅助函数 ──────────────────────────────────────────────────────

def _run_benchmark(func: Callable, number: int = 10, repeat: int = 3) -> Tuple[float, float]:
    """运行 timeit 基准测试，返回 (best_latency_ms, throughput)."""
    timer = timeit.Timer(func)
    # 快速预热
    try:
        timer.timeit(number=1)
    except Exception:
        pass
    results = timer.repeat(repeat=repeat, number=number)
    best_total = min(results)
    avg_latency_ms = (best_total / number) * 1000.0
    throughput = number / best_total if best_total > 0 else 0.0
    return avg_latency_ms, throughput


def _model_exists() -> bool:
    """检查 BGE 模型是否已下载。"""
    model_path = os.path.join(PROJECT_ROOT, "models", "BAAI", "bge-small-zh")
    return os.path.exists(model_path)


# ── pytest 标记 ────────────────────────────────────────────────────

bge_model_missing = pytest.mark.skipif(
    not _model_exists(),
    reason="BGE model not downloaded (models/BAAI/bge-small-zh missing)",
)


# ═══════════════════════════════════════════════════════════════════════════════
# 基准测试类
# ═══════════════════════════════════════════════════════════════════════════════

class TestBenchmark:
    """pytest 风格的基准测试类。"""

    @pytest.fixture(scope="class")
    def pipeline(self):
        """复用 DiscoursePipeline 实例（减少初始化开销）。"""
        pipe = DiscoursePipeline()
        # 预热
        try:
            pipe.process_turn(WARMUP_TEXT, turn_index=0)
        except Exception:
            pass
        yield pipe

    @pytest.fixture(scope="class")
    def encoder(self):
        """获取语义编码器（如可用）。"""
        try:
            from core.agent.compiler.semantic_encoder import get_encoder
            enc = get_encoder()
            return enc
        except Exception:
            return None

    @pytest.fixture(scope="class")
    def segmenter(self):
        return Segmenter()

    @pytest.fixture(scope="class")
    def injector(self):
        return HeaderInjector()

    @pytest.fixture(scope="class")
    def decomposer(self):
        return SyntacticDecomposer()

    @pytest.fixture(scope="class")
    def quantizer(self):
        return MacroMicroQuantizer(embedding_model_name=None)

    # ── BGE 编码基准 ────────────────────────────────────────────

    @bge_model_missing
    def test_encode_single(self, encoder):
        """BGE encode 单条文本延迟。"""
        if encoder is None:
            pytest.skip("Encoder unavailable")

        def _encode():
            encoder.encode("帮我写 Python 脚本")

        latency_ms, throughput = _run_benchmark(_encode, number=10, repeat=3)
        print(f"\n[test_encode_single] latency={latency_ms:.2f}ms, throughput={throughput:.2f} encodes/sec")
        assert latency_ms > 0

    @bge_model_missing
    def test_encode_batch(self, encoder):
        """BGE encode 批量 10 条文本延迟。"""
        if encoder is None:
            pytest.skip("Encoder unavailable")

        def _encode_batch():
            encoder.encode(BATCH_TEXTS)

        latency_ms, throughput = _run_benchmark(_encode_batch, number=10, repeat=3)
        print(f"\n[test_encode_batch] latency={latency_ms:.2f}ms/batch, throughput={throughput:.2f} batches/sec")
        assert latency_ms > 0

    # ── 完整 Pipeline 基准 ────────────────────────────────────────

    def test_process_turn(self, pipeline):
        """单轮完整 pipeline 延迟。"""
        def _process():
            pipeline.process_turn("帮我写 Python 脚本分析 Redis 数据", turn_index=0)

        latency_ms, throughput = _run_benchmark(_process, number=5, repeat=3)
        print(f"\n[test_process_turn] latency={latency_ms:.2f}ms, throughput={throughput:.2f} turns/sec")
        assert latency_ms > 0

    def test_process_10_turns(self, pipeline):
        """10 轮端到端延迟。"""
        # 先重置，确保状态干净
        pipeline.reset()
        turn = 0

        def _process_10():
            nonlocal turn
            for i in range(10):
                pipeline.process_turn(
                    f"第{i}轮测试输入，帮我分析 Python 性能",
                    turn_index=turn + i,
                )
            turn += 10

        latency_ms, throughput = _run_benchmark(_process_10, number=3, repeat=2)
        print(f"\n[test_process_10_turns] total_latency={latency_ms * 3:.2f}ms, per_turn={latency_ms:.2f}ms, throughput={throughput:.2f} turns/sec")
        assert latency_ms > 0

    # ── 组件级基准 ────────────────────────────────────────────────

    def test_segmenter(self, segmenter):
        """纯 Segmenter 切分延迟。"""
        edus = []
        for i in range(5):
            edu = EDU(
                id=f"edu:T0:U{i}",
                turn_index=0,
                edu_index=i,
                raw_text=f"测试句子{i}，包含 Python 和 Redis",
                micro_dimensions=MicroDimensions(μ1=0.5, μ2=0.3, μ3=0.2, μ4=0.1, μ5=0.0),
                macro_dimensions=MacroDimensions(M1=0.6, M2=0.4, M3=0.3, M4=0.8),
            )
            edus.append(edu)

        def _segment():
            segmenter.segment(edus)

        latency_ms, throughput = _run_benchmark(_segment, number=100, repeat=3)
        print(f"\n[test_segmenter] latency={latency_ms:.2f}ms, throughput={throughput:.2f} segments/sec")
        assert latency_ms > 0

    def test_header_inject(self, injector):
        """纯 HeaderInjector 延迟。"""
        def _inject():
            injector.inject("帮我分析它", session_id="bench", session_history=None, turn_index=0)

        latency_ms, throughput = _run_benchmark(_inject, number=50, repeat=3)
        print(f"\n[test_header_inject] latency={latency_ms:.2f}ms, throughput={throughput:.2f} injects/sec")
        assert latency_ms > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 纯 Python 运行入口（无需 pytest）
# ═══════════════════════════════════════════════════════════════════════════════

def _run_standalone():
    """纯 Python 独立运行所有基准测试。"""
    print("=" * 60)
    print("Discourse Block Tree — Standalone Benchmark")
    print("=" * 60)

    # 初始化组件
    pipeline = DiscoursePipeline()
    segmenter = Segmenter()
    injector = HeaderInjector()

    try:
        from core.agent.compiler.semantic_encoder import get_encoder
        encoder = get_encoder()
    except Exception:
        encoder = None

    # 预热
    try:
        pipeline.process_turn(WARMUP_TEXT, turn_index=0)
    except Exception:
        pass

    print(f"\nBGE model available: {'YES' if _model_exists() else 'NO'}")
    print(f"Encoder initialized: {'YES' if encoder else 'NO'}")
    print()

    # 1. encode_single
    if encoder and _model_exists():
        def _encode_single():
            encoder.encode("帮我写 Python 脚本")
        latency_ms, throughput = _run_benchmark(_encode_single, number=10, repeat=3)
        print(f"[encode_single]   latency={latency_ms:>8.2f}ms   throughput={throughput:>8.2f} encodes/sec")
    else:
        print("[encode_single]   SKIPPED (BGE model not available)")

    # 2. encode_batch
    if encoder and _model_exists():
        def _encode_batch():
            encoder.encode(BATCH_TEXTS)
        latency_ms, throughput = _run_benchmark(_encode_batch, number=10, repeat=3)
        print(f"[encode_batch]    latency={latency_ms:>8.2f}ms   throughput={throughput:>8.2f} batches/sec")
    else:
        print("[encode_batch]    SKIPPED (BGE model not available)")

    # 3. process_turn
    def _process_turn():
        pipeline.process_turn("帮我写 Python 脚本分析 Redis 数据", turn_index=0)
    latency_ms, throughput = _run_benchmark(_process_turn, number=5, repeat=3)
    print(f"[process_turn]    latency={latency_ms:>8.2f}ms   throughput={throughput:>8.2f} turns/sec")

    # 4. process_10_turns
    turn_counter = 0
    def _process_10():
        nonlocal turn_counter
        for i in range(10):
            pipeline.process_turn(f"第{i}轮测试输入", turn_index=turn_counter + i)
        turn_counter += 10
    latency_ms, throughput = _run_benchmark(_process_10, number=3, repeat=2)
    print(f"[process_10_turns] latency={latency_ms:>8.2f}ms/turn throughput={throughput:>8.2f} turns/sec")

    # 5. segmenter
    edus = []
    for i in range(5):
        edu = EDU(
            id=f"edu:T0:U{i}",
            turn_index=0,
            edu_index=i,
            raw_text=f"测试句子{i}，包含 Python 和 Redis",
            micro_dimensions=MicroDimensions(μ1=0.5, μ2=0.3, μ3=0.2, μ4=0.1, μ5=0.0),
            macro_dimensions=MacroDimensions(M1=0.6, M2=0.4, M3=0.3, M4=0.8),
        )
        edus.append(edu)
    def _segment():
        segmenter.segment(edus)
    latency_ms, throughput = _run_benchmark(_segment, number=100, repeat=3)
    print(f"[segmenter]       latency={latency_ms:>8.2f}ms   throughput={throughput:>8.2f} segments/sec")

    # 6. header_inject
    def _header_inject():
        injector.inject("帮我分析它", session_id="bench", session_history=None, turn_index=0)
    latency_ms, throughput = _run_benchmark(_header_inject, number=50, repeat=3)
    print(f"[header_inject]   latency={latency_ms:>8.2f}ms   throughput={throughput:>8.2f} injects/sec")

    print("\n" + "=" * 60)
    print("Benchmark completed")
    print("=" * 60)


if __name__ == "__main__":
    _run_standalone()
