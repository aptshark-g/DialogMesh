# core/infrastructure/test_runner.py
"""自动化测试框架 — 集成测试 + 性能基准 + 回归测试。

测试模块：
    test_topic_detection — 话题切换检测准确率
    test_semantic_search — 语义搜索召回率/精确率
    test_persistence — 持久化一致性
    test_graph_store — 图数据库操作
    test_model_service — 模型服务可用性

使用方式：
    from core.infrastructure.test_runner import run_all_tests

    results = run_all_tests()
    # → {"passed": 5, "failed": 0, "details": [...]}
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float
    message: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


class TestRunner:
    """自动化测试运行器。"""

    def __init__(self):
        self.results: List[TestResult] = []

    def run(self, name: str, test_fn: Callable[[], Optional[Dict[str, Any]]]) -> TestResult:
        """运行单个测试。"""
        start = time.time()
        try:
            metrics = test_fn()
            if metrics is None:
                metrics = {}
            duration = (time.time() - start) * 1000
            result = TestResult(name=name, passed=True, duration_ms=duration, metrics=metrics)
        except Exception as e:
            duration = (time.time() - start) * 1000
            result = TestResult(
                name=name, passed=False, duration_ms=duration,
                message=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}",
            )
        self.results.append(result)
        return result

    def report(self) -> Dict[str, Any]:
        """生成测试报告。"""
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total if total > 0 else 0.0,
            "total_duration_ms": sum(r.duration_ms for r in self.results),
            "details": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "duration_ms": round(r.duration_ms, 2),
                    "message": r.message[:200] if not r.passed else "",
                    "metrics": r.metrics,
                }
                for r in self.results
            ],
        }


# ── 测试套件 ───────────────────────────────────────────────────


def test_topic_detection() -> Dict[str, Any]:
    """话题切换检测准确率测试。"""
    import sys
    import os
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\MemoryGraph")

    from core.agent.context_manager.discourse_manager import DiscourseManager
    from core.agent.context_manager.semantic_index import SemanticIndex

    dm = DiscourseManager.__new__(DiscourseManager)
    dm.semantic_index = SemanticIndex()

    test_cases = [
        # (query1, query2, expected_same, desc)
        ("帮我写 Python 函数", "这个函数怎么优化？", True, "编程-延续"),
        ("精密领域一定要上磨床吗？", "如果是切削的话才会更加受到振动影响粗糙度吧？", True, "机械-延续"),
        ("今天赣州天气怎么样？", "帮我写 Python 函数", False, "天气→编程-切换"),
        ("精密领域一定要上磨床吗？", "今天赣州天气怎么样？", False, "机械→天气-切换"),
        ("你知道赣州有什么好吃的吗？", "帮我写 Python 函数", False, "美食→编程-切换"),
    ]

    correct = 0
    scores = []
    for q1, q2, expected_same, desc in test_cases:
        overlap = dm._compute_topic_overlap(q1, q2, context="prev_turn")
        predicted = overlap > 0.45
        is_correct = predicted == expected_same
        if is_correct:
            correct += 1
        scores.append({
            "desc": desc,
            "overlap": round(overlap, 3),
            "predicted": "SAME" if predicted else "SWITCH",
            "expected": "SAME" if expected_same else "SWITCH",
            "correct": is_correct,
        })

    accuracy = correct / len(test_cases)
    return {
        "accuracy": accuracy,
        "threshold": 0.45,
        "cases": len(test_cases),
        "correct": correct,
        "scores": scores,
    }


def test_semantic_search() -> Dict[str, Any]:
    """语义搜索精度测试。"""
    import sys
    import os
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\MemoryGraph")

    from core.agent.context_manager.semantic_index import SemanticIndex

    idx = SemanticIndex()
    idx.warm_up()

    # 索引测试数据
    docs = [
        ("b1", "Python 列表推导式教程"),
        ("b2", "FastAPI 异步 Web 框架"),
        ("b3", "Rust 内存安全与所有权"),
        ("b4", "磨床加工精度控制"),
        ("b5", "表面粗糙度测量方法"),
    ]
    for bid, text in docs:
        idx.add_block(bid, text)

    queries = [
        ("Python 编程", "b1"),
        ("Web 后端框架", "b2"),
        ("Rust 语言", "b3"),
        ("磨床加工", "b4"),
        ("粗糙度测量", "b5"),
    ]

    top1_correct = 0
    in_top3 = 0
    for query, expected_id in queries:
        results = idx.search(query, top_k=3, min_score=0.0)
        if results and results[0][0] == expected_id:
            top1_correct += 1
        if any(r[0] == expected_id for r in results):
            in_top3 += 1

    return {
        "top1_accuracy": top1_correct / len(queries),
        "top3_recall": in_top3 / len(queries),
        "queries": len(queries),
    }


def test_persistence() -> Dict[str, Any]:
    """持久化一致性测试。"""
    import sys
    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\MemoryGraph")

    from core.infrastructure.sqlite_store import get_sqlite_store

    store = get_sqlite_store(db_path="data/test_persistence.db")
    session_id = "persistence_test"

    # 清理
    store.delete_session(session_id)

    # 写入
    store.save_session(session_id, "user_test")
    store.save_turn(session_id, 0, "查询1", topic_id=0, intent="test")
    store.save_turn(session_id, 1, "查询2", topic_id=0, intent="test")
    store.save_topic(session_id, 0, "测试话题", turns=[0, 1], domains=["测试"])

    # 读取
    turns = store.load_turns(session_id)
    topics = store.load_topics(session_id)

    # 验证
    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"
    assert len(topics) == 1, f"Expected 1 topic, got {len(topics)}"
    assert turns[0]["raw_query"] == "查询1", f"Turn 0 query mismatch: {turns[0]['raw_query']}"
    assert topics[0]["name"] == "测试话题", f"Topic name mismatch: {topics[0]['name']}"

    # 清理
    store.delete_session(session_id)

    return {
        "turns": len(turns),
        "topics": len(topics),
        "consistent": True,
    }


def test_graph_store() -> Dict[str, Any]:
    """图数据库操作测试。"""
    import sys
    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\MemoryGraph")

    from core.infrastructure.graph_store import get_graph_store

    g = get_graph_store("test_graph")
    g.clear()

    # 添加话题
    g.add_topic(0, "Python", turns=[0, 1], domains=["Python", "编程"], intent="coding")
    g.add_topic(1, "天气", turns=[2], domains=["赣州"], intent="weather")

    # 添加轮次
    g.add_turn(0, 0, "帮我写 Python", intent="coding")
    g.add_turn(1, 0, "怎么优化？", intent="coding")
    g.add_turn(2, 1, "赣州天气", intent="weather")

    # 添加关系
    g.add_edge(0, 1, relation="switch", weight=0.2)

    # 查询
    topics = g.get_all_topics()
    assert len(topics) == 2, f"Expected 2 topics, got {len(topics)}"

    path = g.get_topic_path(1)
    assert len(path) > 0, "Topic path should not be empty"

    turns = g.get_topic_turns(0)
    assert len(turns) == 2, f"Expected 2 turns in topic 0, got {len(turns)}"

    stats = g.get_stats()
    assert stats["nodes"] >= 5, f"Expected >=5 nodes, got {stats['nodes']}"
    assert stats["edges"] >= 3, f"Expected >=3 edges, got {stats['edges']}"

    g.save()

    return {
        "topics": len(topics),
        "path": path,
        "turns_in_topic_0": len(turns),
        "nodes": stats["nodes"],
        "edges": stats["edges"],
    }


def test_model_service() -> Dict[str, Any]:
    """模型服务可用性测试。"""
    import sys
    import os
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\MemoryGraph")

    from core.infrastructure.model_service import get_model_service

    service = get_model_service()
    ok = service.warm_up()
    assert ok, "Model service warm-up failed"

    vec = service.encode("测试文本")
    assert vec is not None, "Encoding failed"
    assert vec.shape[1] == 512, f"Expected 512-dim, got {vec.shape}"

    stats = service.stats
    return {
        "status": stats["status"],
        "latency_ms": round(stats["latency_ms_avg"], 2),
        "cache_size": stats["cache_size"],
        "dim": vec.shape[1],
    }


# ── 运行入口 ───────────────────────────────────────────────────


def run_all_tests() -> Dict[str, Any]:
    """运行全部测试套件。"""
    runner = TestRunner()

    tests = [
        ("model_service", test_model_service),
        ("persistence", test_persistence),
        ("graph_store", test_graph_store),
        ("topic_detection", test_topic_detection),
        ("semantic_search", test_semantic_search),
    ]

    for name, fn in tests:
        runner.run(name, fn)

    return runner.report()


if __name__ == "__main__":
    results = run_all_tests()
    print(json.dumps(results, ensure_ascii=False, indent=2))
