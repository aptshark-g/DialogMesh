# -*- coding: utf-8 -*-
"""
core/agent/pcr/tests/benchmark.py
──────────────────────────────────
Benchmark harness for PCR implementations.

Measures and compares latency distribution, throughput, and error rates across
different PCR router implementations under controlled load.

Usage:
    from core.agent.pcr.tests.benchmark import Benchmark, BenchmarkConfig
    from core.agent.pcr.rule_based import RuleBasedPCR

    cfg = BenchmarkConfig(duration_sec=5, warmup_sec=1)
    bench = Benchmark(cfg)
    result = bench.run(RuleBasedPCR(), verbose=True)
    result.report()

All pure-Python, zero extra dependencies.
"""

from __future__ import annotations

import time
import statistics
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from core.agent.pcr.interface import IPCRRouter
from core.agent.pcr.datacontract import PCRInput_v1, HistoryEntry


@dataclass
class BenchmarkConfig:
    """Configuration for a benchmark run."""
    duration_sec: float = 5.0       # Total measurement time
    warmup_sec: float = 1.0         # Warm-up before measurement
    max_queries: int = 0            # 0 = unlimited
    query_batch_size: int = 10      # Report interval
    queries: Optional[List[str]] = None  # Custom queries; default = synthetic mix

    # Synthetic query mix (if queries is None)
    synthetic_categories: int = 5   # Number of distinct query patterns


@dataclass
class LatencyDistribution:
    """Latency distribution statistics."""
    samples: List[float] = field(default_factory=list)
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    p999: float = 0.0
    max_ms: float = 0.0
    min_ms: float = 0.0
    avg_ms: float = 0.0
    std_ms: float = 0.0

    def compute(self) -> None:
        if not self.samples:
            return
        s = sorted(self.samples)
        n = len(s)
        self.p50 = s[int(n * 0.50)]
        self.p95 = s[int(n * 0.95)] if n > 20 else s[-1]
        self.p99 = s[int(n * 0.99)] if n > 100 else s[-1]
        self.p999 = s[int(n * 0.999)] if n > 1000 else s[-1]
        self.max_ms = max(s)
        self.min_ms = min(s)
        self.avg_ms = statistics.mean(s)
        self.std_ms = statistics.stdev(s) if n > 1 else 0.0


@dataclass
class BenchmarkResult:
    """Results of a benchmark run."""
    router_name: str = ""
    config: BenchmarkConfig = field(default_factory=BenchmarkConfig)

    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    error_queries: int = 0

    latency: LatencyDistribution = field(default_factory=LatencyDistribution)
    throughput_qps: float = 0.0
    wall_time_sec: float = 0.0

    # Per-category breakdown
    category_counts: Dict[str, int] = field(default_factory=dict)
    category_errors: Dict[str, int] = field(default_factory=dict)

    def report(self) -> str:
        lines = [
            "═" * 60,
            f"  Benchmark Report: {self.router_name}",
            "═" * 60,
            f"  Duration:      {self.wall_time_sec:.2f}s",
            f"  Total:         {self.total_queries}",
            f"  Success:       {self.successful_queries} ({self.success_rate:.1%})",
            f"  Fail:          {self.failed_queries}",
            f"  Error:         {self.error_queries}",
            f"  Throughput:    {self.throughput_qps:.1f} q/s",
            "",
            "  Latency Distribution (ms):",
            f"    avg   = {self.latency.avg_ms:.3f}",
            f"    min   = {self.latency.min_ms:.3f}",
            f"    p50   = {self.latency.p50:.3f}",
            f"    p95   = {self.latency.p95:.3f}",
            f"    p99   = {self.latency.p99:.3f}",
            f"    p99.9 = {self.latency.p999:.3f}",
            f"    max   = {self.latency.max_ms:.3f}",
            f"    std   = {self.latency.std_ms:.3f}",
            "═" * 60,
        ]
        return "\n".join(lines)

    @property
    def success_rate(self) -> float:
        return self.successful_queries / max(1, self.total_queries)


class Benchmark:
    """Benchmark harness for PCR routers."""

    _DEFAULT_QUERIES = [
        # Tool expectations
        "scan the binary", "patch the function", "read 0x401000", "write 0x100 bytes",
        "set breakpoint on main", "dump the registers", "hook the import table",
        "trace execution flow", "attach to process 1234", "detach from process",
        "disassemble the function", "find string references",
        # Ambiguous / edge cases
        "analyze this", "what does this do", "help me", "explain the function",
        # Chinese
        "扫描这个函数", "修改这里的内存", "下断点", "读取寄存器",
        # Complex
        "if the function is hooked, scan it otherwise trace it",
        "first attach, then breakpoint, then dump, then scan",
        # Short
        "scan", "patch", "read", "hook",
    ]

    def __init__(self, config: Optional[BenchmarkConfig] = None):
        self._cfg = config or BenchmarkConfig()
        self._queries = self._cfg.queries or self._DEFAULT_QUERIES

    def run(self, router: IPCRRouter, verbose: bool = False) -> BenchmarkResult:
        """Run the benchmark against a router."""
        result = BenchmarkResult(router_name=router.name, config=self._cfg)
        queries = self._queries

        # Warm-up
        if verbose:
            print(f"Warming up for {self._cfg.warmup_sec}s...")
        warmup_end = time.perf_counter() + self._cfg.warmup_sec
        while time.perf_counter() < warmup_end:
            for q in queries:
                try:
                    router.evaluate(PCRInput_v1(query=q, session_history=[], metadata={}))
                except Exception:
                    pass

        # Measurement
        if verbose:
            print(f"Benchmarking for {self._cfg.duration_sec}s...")
        start = time.perf_counter()
        end = start + self._cfg.duration_sec
        query_idx = 0
        next_report = start + 0.5

        while time.perf_counter() < end:
            q = queries[query_idx % len(queries)]
            query_idx += 1

            inp = PCRInput_v1(query=q, session_history=[], metadata={})
            t0 = time.perf_counter()
            try:
                out = router.evaluate(inp)
                latency = (time.perf_counter() - t0) * 1000
                result.latency.samples.append(latency)
                result.successful_queries += 1
                result.category_counts[out.expectation] = result.category_counts.get(out.expectation, 0) + 1
            except Exception:
                latency = (time.perf_counter() - t0) * 1000
                result.latency.samples.append(latency)
                result.error_queries += 1
                result.category_errors["_ERROR"] = result.category_errors.get("_ERROR", 0) + 1

            result.total_queries += 1

            if self._cfg.max_queries > 0 and result.total_queries >= self._cfg.max_queries:
                break

            if verbose and time.perf_counter() >= next_report:
                elapsed = time.perf_counter() - start
                qps = result.total_queries / elapsed if elapsed > 0 else 0
                print(f"  {elapsed:.1f}s: {result.total_queries} queries, {qps:.0f} q/s")
                next_report += 0.5

        result.wall_time_sec = time.perf_counter() - start
        result.latency.compute()
        result.throughput_qps = result.total_queries / max(0.001, result.wall_time_sec)
        return result


# ───────────────────────────────────────────────────────────────────────────────
# Comparative benchmark
# ───────────────────────────────────────────────────────────────────────────────

def compare_routers(
    routers: List[IPCRRouter],
    config: Optional[BenchmarkConfig] = None,
    verbose: bool = False,
) -> Dict[str, BenchmarkResult]:
    """Run the same benchmark configuration against multiple routers."""
    results: Dict[str, BenchmarkResult] = {}
    for router in routers:
        if verbose:
            print(f"\n--- Benchmarking {router.name} ---")
        bench = Benchmark(config)
        result = bench.run(router, verbose=verbose)
        results[router.name] = result
        if verbose:
            print(result.report())
    return results


def print_comparison(results: Dict[str, BenchmarkResult]) -> None:
    """Print a side-by-side comparison table."""
    names = list(results.keys())
    if not names:
        print("No results to compare.")
        return

    print("\n" + "═" * 80)
    print(f"{'Router':<20} {'q/s':>8} {'p50(ms)':>10} {'p95(ms)':>10} {'p99(ms)':>10} {'err%':>8} {'success%':>10}")
    print("─" * 80)
    for name in names:
        r = results[name]
        err_pct = (r.error_queries / max(1, r.total_queries)) * 100
        print(
            f"{name:<20} "
            f"{r.throughput_qps:>8.1f} "
            f"{r.latency.p50:>10.3f} "
            f"{r.latency.p95:>10.3f} "
            f"{r.latency.p99:>10.3f} "
            f"{err_pct:>8.1f} "
            f"{r.success_rate:>10.1%}"
        )
    print("═" * 80)


# ───────────────────────────────────────────────────────────────────────────────
# Latency profile generator (for capacity planning)
# ───────────────────────────────────────────────────────────────────────────────

def latency_profile(router: IPCRRouter, query: str = "scan the binary", iterations: int = 1000) -> LatencyDistribution:
    """Generate a detailed latency profile for a single query."""
    samples: List[float] = []
    inp = PCRInput_v1(query=query, session_history=[], metadata={})
    for _ in range(iterations):
        t0 = time.perf_counter()
        try:
            router.evaluate(inp)
        except Exception:
            pass
        samples.append((time.perf_counter() - t0) * 1000)
    dist = LatencyDistribution(samples=samples)
    dist.compute()
    return dist


# ───────────────────────────────────────────────────────────────────────────────
# CLI helper (can be run standalone if needed)
# ───────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.path.insert(0, "C:/Users/APTShark/PycharmProjects/MemoryGraph")

    from core.agent.pcr.rule_based import RuleBasedPCR
    from core.agent.pcr.tests.mock_pcr import StaticMockPCR

    cfg = BenchmarkConfig(duration_sec=3, warmup_sec=0.5)
    results = compare_routers(
        [RuleBasedPCR(), StaticMockPCR()],
        config=cfg,
        verbose=True,
    )
    print_comparison(results)
