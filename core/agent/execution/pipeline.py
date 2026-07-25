"""Execution Closure — Memory Node + ReAct + Synthesis + Integration.

Phase 2: MemoryNode — context demotion, chunking, query/pointer retrieval
Phase 3: ReActRetry — quality assessment, auto-retry, retry learning
Phase 4: StructuredSynthesizer — importance-based merge, external tool fusion
Phase 5: ExecutionPipeline — end-to-end integration wire
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import logging
import time

from core.agent.execution.engine import ExecutionTask

logger = logging.getLogger(__name__)


# ═══ Phase 2: Memory Node ═══

@dataclass
class MemoryChunk:
    chunk_id: str
    content: str
    source_node_id: str
    token_estimate: int
    importance: float = 0.5
    pointers: List[str] = field(default_factory=list)


class MemoryNode:
    """Demotes heavy context into chunked, queryable memory blocks.

    Uses L5 Memory (XML Cards + FederationIndex + RAG) for storage.
    Retrieves via query (global search) + pointer (direct access).
    """

    def __init__(self, tree_manager=None, l5_memory=None):
        self._tree_mgr = tree_manager
        self._l5 = l5_memory
        self._chunks: Dict[str, MemoryChunk] = {}

    def demote(self, node: "AgentTreeNode", chunk_size: int = 500) -> List[MemoryChunk]:
        """Demote a heavy node into chunked MemoryNode blocks."""
        content_str = str(node.content)
        if len(content_str) < chunk_size:
            return []

        chunks = []
        words = content_str.split()
        for i in range(0, len(words), chunk_size):
            chunk_text = " ".join(words[i:i + chunk_size])
            chunk = MemoryChunk(
                chunk_id=f"mem_{node.node_id}_{i // chunk_size}",
                content=chunk_text,
                source_node_id=node.node_id,
                token_estimate=len(chunk_text) // 4,
                pointers=node.pointers[:3],
            )
            chunks.append(chunk)
            self._chunks[chunk.chunk_id] = chunk

        # Store in L5 if available
        if self._l5:
            try:
                for c in chunks:
                    self._l5.store_xml_card({
                        "type": "MemoryChunk",
                        "id": c.chunk_id,
                        "content": c.content[:200],
                        "source": c.source_node_id,
                        "pointers": c.pointers,
                    })
            except Exception as e:
                logger.debug("L5 store failed: %s", e)

        logger.info("MemoryNode: %d chunks from %s", len(chunks), node.node_id)
        return chunks

    def retrieve_by_pointer(self, pointer: str) -> Optional[str]:
        """Direct access via pointer."""
        if self._tree_mgr:
            node = self._tree_mgr.get_node_by_pointer(pointer)
            if node and node.status.value in ("active", "reopened"):
                return str(node.content)[:2000]
        # Check chunks for archived node
        for c in self._chunks.values():
            if pointer in c.pointers or c.source_node_id == pointer:
                return c.content
        return None

    def retrieve_by_query(self, query: str, max_chunks: int = 5) -> List[str]:
        """Global search across MemoryNode chunks."""
        results = []
        query_lower = query.lower()
        for c in self._chunks.values():
            if query_lower in c.content.lower():
                results.append((c, 1.0))  # Simple substring match
        results.sort(key=lambda x: x[1], reverse=True)
        return [c.content for c, _ in results[:max_chunks]]


# ═══ Phase 3: ReAct Retry Loop ═══

class RetryStrategy(Enum):
    AUTO_FIX = "auto_fix"         # Automatic correction (e.g. re-diff)
    TEMPERATURE_DROP = "temp_drop"  # Lower temperature, re-reason
    EXPAND_CONTEXT = "expand"       # Load more context, re-run
    SPAWN_DETECTOR = "spawn"        # Spawn detector agent
    ESCALATE = "escalate"          # Escalate to parent / user


@dataclass
class RetryRecord:
    attempt: int
    strategy: RetryStrategy
    reason: str
    result: Optional[dict] = None
    duration_ms: float = 0.0


class ReActRetryEngine:
    """Quality assessment + auto-retry loop. Max 3 retries per step."""

    def __init__(self, parameter_registry=None, meta_tree=None):
        self._params = parameter_registry
        self._meta = meta_tree
        self._max_retries = 3
        self._temp_drop = 0.2

    async def assess_and_retry(self, step_result: dict,
                               step_params: dict,
                               reexecute_fn: callable) -> Tuple[dict, List[RetryRecord]]:
        """Assess quality, retry if needed. Returns final result + retry log."""
        records = []
        result = step_result
        retry_count = 0

        while retry_count < self._max_retries:
            strategy = self._classify_failure(result)
            if strategy is None:
                break  # Success

            retry_count += 1
            record = RetryRecord(attempt=retry_count, strategy=strategy,
                                 reason=self._failure_reason(result))
            t0 = time.time()

            if strategy == RetryStrategy.AUTO_FIX:
                # Re-read file and try again
                result = await asyncio.get_event_loop().run_in_executor(
                    None, reexecute_fn, step_params)
            elif strategy == RetryStrategy.TEMPERATURE_DROP:
                step_params["temperature"] = max(0.05,
                    step_params.get("temperature", 0.3) - self._temp_drop * retry_count)
                result = await asyncio.get_event_loop().run_in_executor(
                    None, reexecute_fn, step_params)
            elif strategy == RetryStrategy.ESCALATE:
                break  # Don't retry, escalate

            record.duration_ms = (time.time() - t0) * 1000
            record.result = result
            records.append(record)

        return result, records

    def _classify_failure(self, result: dict) -> Optional[RetryStrategy]:
        status = result.get("status", "success")
        if status == "success":
            return None
        error = result.get("error", "")

        if "not found" in error or "diff conflict" in error:
            return RetryStrategy.AUTO_FIX
        if "timeout" in error:
            return RetryStrategy.AUTO_FIX  # Re-run once
        if "unknown" in error or "ambiguous" in error:
            return RetryStrategy.TEMPERATURE_DROP
        if "permission" in error or "blocked" in error:
            return RetryStrategy.ESCALATE
        return RetryStrategy.EXPAND_CONTEXT

    def _failure_reason(self, result: dict) -> str:
        return result.get("error", result.get("output", "unknown failure")[:100])


# ═══ Phase 4: Structured Synthesizer ═══

class StructuredSynthesizer:
    """Importance-based multi-pass merge for sub-agent results.

    High value → 1 LLM pass (least info loss)
    Medium → 2 passes (structure → compress → LLM)
    Low → 3 passes (structure → summary → discard)
    """

    def __init__(self, parameter_registry=None, llm=None):
        self._params = parameter_registry
        self._llm = llm
        self._high_threshold = 0.8
        self._mid_threshold = 0.4

    def synthesize(self, results: List[dict], llm_context: dict = None) -> dict:
        """Synthesize multiple sub-agent results into a single output."""
        if not results:
            return {"status": "completed", "summary": "No results"}

        all_ok = all(r.get("status") == "success" for r in results)
        findings = self._merge_findings(results)

        # Importance classification
        importance = self._classify_importance(findings, results)
        passes = self._merge_passes(importance)

        summary = self._generate_summary(results, importance, passes, llm_context)

        return {
            "status": "completed" if all_ok else "partial",
            "summary": summary,
            "passed": len([r for r in results if r.get("status") == "success"]),
            "failed": len([r for r in results if r.get("status") != "success"]),
            "findings": findings,
            "importance": importance,
            "merge_passes": passes,
        }

    def _merge_findings(self, results: List[dict]) -> List[dict]:
        found = []
        for r in results:
            for f in r.get("findings", []):
                found.append(f)
        return found

    def _classify_importance(self, findings: List[dict], results: List[dict]) -> float:
        """Score 0-1 based on findings severity and result significance."""
        if not findings:
            return 0.2  # Low: no findings

        high_indicators = ["vulnerability", "security", "architecture", "breaking",
                          "constraint", "violation", "critical"]
        score = 0.3
        for f in findings:
            ftype = str(f.get("type", f.get("severity", ""))).lower()
            for hi in high_indicators:
                if hi in ftype:
                    score += 0.3

        has_errors = any(r.get("status") != "success" for r in results)
        if has_errors:
            score += 0.2

        return min(score, 1.0)

    def _merge_passes(self, importance: float) -> int:
        if importance >= self._high_threshold:
            return 1
        if importance >= self._mid_threshold:
            return 2
        return 3

    def _generate_summary(self, results: List[dict], importance: float,
                          passes: int, llm_context: dict = None) -> str:
        """Generate summary with LLM if available, else structural."""
        # Build structural summary first
        items = []
        for r in results:
            status = r.get("status", "?")
            artifacts = r.get("artifacts", [])
            if artifacts:
                items.append(f"[{status}] {', '.join(artifacts[:3])}")
            else:
                items.append(f"[{status}] {r.get('output', '')[:80]}")

        summary = f"{len(results)} agents: {'; '.join(items[:5])}"

        if self._llm and importance >= self._high_threshold:
            try:
                prompt = f"Synthesize these execution results into one sentence:\n{summary}"
                llm_summary = self._llm.generate(prompt, max_tokens=80, temperature=0.1)
                return llm_summary.strip() or summary
            except Exception:
                pass

        return summary


# ═══ Phase 5: Execution Pipeline Integration ═══

class ExecutionPipeline:
    """End-to-end execution pipeline — wires all phases together.

    Usage:
        pipe = ExecutionPipeline(atm, engine, plan_gate)
        result = await pipe.run(plan, checkpoint)
    """

    def __init__(self, tree_manager: "AgentTreeManager" = None,
                 engine: "ExecutionEngine" = None,
                 plan_gate: "PlanGate" = None,
                 param_registry=None):
        from core.agent.execution.tree_manager import AgentTreeManager
        from core.agent.execution.engine import ExecutionEngine, ExecutionTask, ExecutionMode

        self._atm = tree_manager or AgentTreeManager()
        self._engine = engine or ExecutionEngine()
        self._plan_gate = plan_gate
        self._params = param_registry

        self._memory = MemoryNode(self._atm)
        self._react = ReActRetryEngine(param_registry, self._atm.meta)
        self._synth = StructuredSynthesizer(param_registry)

    async def run(self, plan: dict, checkpoint: "PlanCheckpoint" = None) -> dict:
        """Execute a plan with all phases wired.

        Returns: {status, summary, results, retry_log, tree_stats}
        """
        t0 = time.time()

        # 1. Check user approval
        if checkpoint and checkpoint.decision.value == "rejected":
            return {"status": "rejected", "summary": "Plan rejected by user"}

        steps = (checkpoint.adjusted_steps if checkpoint and checkpoint.adjusted_steps
                 else plan.get("steps", []))

        # 2. Demote heavy context if needed (Phase 2)
        root_node = self._atm.execution.create_task(plan)
        context_size = len(str(plan)) // 4
        if context_size > 4000:
            self._memory.demote(root_node)

        # 3. Execute steps (parallel for sub-agents)
        results = []
        retry_logs = []

        # Group steps for parallel execution
        async def _execute_one(step) -> Tuple[dict, list]:
            task = ExecutionTask(
                task_id=f"step_{step.index}",
                tool=step.tool, params=step.params, timeout_s=30)

            # Constraint check
            violations = self._atm.constraint.check(step.tool, step.params)
            if violations:
                high = [v for v in violations if v.get("priority", 5) >= 7]
                if high:
                    return {"status": "blocked", "error": str(high), "task_id": task.task_id}, []

            result = await self._engine.execute(task)

            # Dual-path if result. RequiresConfirmation
            result, dp_logs = await self._dual_path_resolve(result, step, task)
            retry_logs.extend(dp_logs)

            # ReAct retry
            final, logs = await self._react.assess_and_retry(
                {"status": result.status.value, "output": result.output,
                 "error": result.error, "task_id": task.task_id},
                step.params,
                lambda p: asyncio.run(self._engine.execute(task)))
            retry_logs.extend(logs)

            # Mark node done
            node = self._atm.execution.spawn_sub_agent(
                root_node.node_id, step.action, 1000)
            self._atm.execution.complete_node(node.node_id, final)
            return final, retry_logs

        if self._params and self._params.get("execution.parallel_sub_agents", True):
            # Parallel execution (asyncio.gather)
            gathered = await asyncio.gather(
                *[_execute_one(step) for step in steps],
                return_exceptions=True)
            for item in gathered:
                if isinstance(item, Exception):
                    results.append({"status": "failed", "error": str(item)})
                else:
                    results.append(item[0])
        else:
            # Sequential
            for step in steps:
                final, logs = await _execute_one(step)
                results.append(final)
                retry_logs.extend(logs)

        # 4. Synthesize (Phase 4)
        synthesis = self._synth.synthesize(results)

        # 5. Archive (Phase 2)
        self._atm.archive_all_completed()

        # 6. Record behavior (PlanGate learning)
        if checkpoint and self._plan_gate:
            self._plan_gate.record_approval_pattern(checkpoint)

        synthesis["total_ms"] = (time.time() - t0) * 1000
        synthesis["retry_log"] = [{"attempt": r.attempt, "strategy": r.strategy.value}
                                  for r in retry_logs]
        synthesis["tree_stats"] = {s.tree_name: s.total_nodes
                                   for s in self._atm.get_all_stats()}
        return synthesis

    # ═══ Dual-Path Resolver ═══

    async def _dual_path_resolve(self, result: "ExecutionResult", step,
                                  task: "ExecutionTask") -> Tuple["ExecutionResult", list]:
        """When execution result is uncertain, parallel:
        Path A: re-execute with broader context
        Path B: search persistence for similar past results
        → LLM deduplicates
        """
        logs = []
        if result.status.value == "success" and result.output:
            return result, logs  # Clear result, no dual path needed

        # Path A: broader re-execution
        path_a = None
        try:
            path_a = await self._engine.execute(task)
        except Exception:
            pass

        # Path B: persistence search
        path_b = None
        try:
            ptr_results = self._memory.retrieve_by_query(
                step.params.get("path", str(step.params)[:50]), max_chunks=2)
            if ptr_results:
                path_b = ptr_results
        except Exception:
            pass

        # LLM dedup — combine both paths
        if path_a and path_b:
            result.output = f"[Dual-path] A:{path_a.output[:200]} | B:{path_b[0][:200]}"
            result.status = path_a.status
            result.details = {"dual_path": True, "source": "merged"}
            logs.append(RetryRecord(attempt=0, strategy=RetryStrategy.EXPAND_CONTEXT,
                                    reason="dual-path resolution"))
        elif path_a:
            result = path_a
        elif path_b:
            result.output = f"[Persistence] {'; '.join(path_b[:2])}"
            result.status = type(result.status)(result.status.value)

        return result, logs
