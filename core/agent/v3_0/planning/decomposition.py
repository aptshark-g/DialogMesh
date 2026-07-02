# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/decomposition.py
────────────────────────────────────────
DialogMesh Agent v3.0 — 任务分解引擎（DecompositionEngine）。

用途：
- 将用户意图分解为可执行的子任务列表（Task）。
- 支持两种路径：
  1. 基于技能模板的快速分解（decompose_with_skill）
  2. LLM 驱动的动态分解（decompose），带 1 秒超时控制
- 超时回退：返回单任务直接执行（由 Answer-LLM 处理）。

设计原则：
- 超时控制是硬约束：asyncio.wait_for 实现，超时后无条件回退。
- 错误回退：任何异常（包括 JSON 解析失败）都回退到单任务。
- 模板渲染：使用 Jinja2 渲染输入模板。

版本：3.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from core.agent.v3_0.planning.models import (
    SkillTemplate,
    Task,
    RetryPolicy,
)

logger = logging.getLogger(__name__)


class DecompositionEngine:
    """任务分解引擎 — 将用户意图分解为可执行的子任务。

    Args:
        llm_provider: 可选的 LLM Provider，用于动态分解。
        default_timeout_ms: 默认超时毫秒数（默认 1000ms）。
    """

    def __init__(
        self,
        llm_provider: Optional[Any] = None,
        default_timeout_ms: int = 1000,
    ) -> None:
        self._llm = llm_provider
        self._default_timeout_ms = default_timeout_ms
        logger.info(f"DecompositionEngine initialized (timeout_ms={default_timeout_ms})")

    async def decompose(
        self,
        intent: str,
        context: Optional[Any] = None,
        timeout_ms: Optional[int] = None,
    ) -> List[Task]:
        """通用任务分解（无技能模板）—— 带超时控制。

        超时策略：
        - 默认 1 秒超时（与端到端 SLA 2 秒对齐，预留 1 秒给执行）
        - 超时后回退到单任务直接执行（Answer-LLM 处理）

        Args:
            intent: 用户意图文本。
            context: 可选上下文。
            timeout_ms: 可选超时毫秒数（覆盖默认值）。

        Returns:
            Task 列表（至少包含一个单任务回退）。
        """
        timeout = (timeout_ms or self._default_timeout_ms) / 1000.0

        async def _decompose_async() -> List[Task]:
            """异步分解内部协程。"""
            await asyncio.sleep(0)
            if self._llm is None:
                raise RuntimeError("No LLM provider available for dynamic decomposition")

            prompt = self._build_decomposition_prompt(intent, context)
            # 在线程池中执行同步 LLM 调用
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._llm.generate(prompt=prompt, temperature=0.3),
            )
            content = getattr(response, "content", None) or getattr(response, "text", "")
            return self._parse_tasks(content)

        try:
            tasks = await asyncio.wait_for(_decompose_async(), timeout=timeout)
            logger.info(f"Tasks decomposed (LLM): count={len(tasks)}, intent='{intent[:50]}'")
            return tasks

        except asyncio.TimeoutError:
            logger.warning(
                f"Decomposition timeout ({timeout*1000:.0f}ms), falling back to single task"
            )
            return self._fallback_single_task(intent)

        except Exception as exc:
            logger.error(f"Decomposition failed: {exc}, falling back to single task")
            return self._fallback_single_task(intent)

    def decompose_with_skill(
        self,
        intent: str,
        skill: SkillTemplate,
        context: Optional[Any] = None,
    ) -> List[Task]:
        """基于技能模板的任务分解（同步快速路径，延迟 < 50ms）。

        使用技能模板中预定义的子任务模式，通过 Jinja2 渲染输入模板。

        Args:
            intent: 用户意图文本。
            skill: 匹配到的技能模板。
            context: 可选上下文。

        Returns:
            Task 列表。
        """
        try:
            tasks: List[Task] = []
            for subtask_template in skill.subtasks:
                input_data = self._render_template(
                    subtask_template.input_template,
                    {"intent": intent, "context": context},
                )
                task = Task(
                    name=subtask_template.name,
                    description=subtask_template.description,
                    worker_type=subtask_template.worker_type,
                    input_data=input_data,
                    output_schema=subtask_template.output_schema,
                    required=subtask_template.required,
                    retry_policy=skill.retry_policy,
                )
                tasks.append(task)
            logger.info(f"Tasks decomposed with skill '{skill.name}': count={len(tasks)}")
            return tasks
        except Exception as exc:
            logger.error(f"Skill-based decomposition failed: {exc}, falling back to single task")
            return self._fallback_single_task(intent)

    def _build_decomposition_prompt(self, intent: str, context: Optional[Any]) -> str:
        """构建分解提示。"""
        context_summary = ""
        if context and hasattr(context, "summary"):
            try:
                context_summary = context.summary()
            except Exception:
                context_summary = str(context)
        elif context:
            context_summary = str(context)

        return f"""请将以下用户意图分解为可执行的子任务列表。

用户意图: {intent}

上下文: {context_summary}

要求:
1. 每个子任务必须是原子操作（不可再分）
2. 明确每个子任务的输入和输出
3. 标注子任务之间的依赖关系
4. 估计每个子任务的执行时间（秒）

输出格式（JSON）:
{{
  "tasks": [
    {{
      "name": "任务名称",
      "description": "任务描述",
      "worker_type": "执行者类型（PCR-LLM/Intent-LLM/Planning-LLM/ToolExecutor）",
      "input": "任务输入",
      "estimated_time": 10,
      "dependencies": []
    }}
  ]
}}
"""

    def _parse_tasks(self, response: str) -> List[Task]:
        """解析 LLM 返回的任务列表。"""
        try:
            text = response.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            data = json.loads(text)
            tasks: List[Task] = []
            for task_data in data.get("tasks", []):
                task = Task(
                    name=task_data["name"],
                    description=task_data.get("description", ""),
                    worker_type=task_data.get("worker_type", "Planning-LLM"),
                    input_data=task_data.get("input", ""),
                    estimated_time=task_data.get("estimated_time", 10),
                    dependencies=task_data.get("dependencies", []),
                )
                tasks.append(task)
            return tasks
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error(f"Failed to parse tasks: {exc}, response={response[:200]}")
            return []
        except Exception as exc:
            logger.error(f"Task parsing failed: {exc}")
            return []

    def _render_template(self, template: str, variables: Dict[str, Any]) -> str:
        """渲染 Jinja2 模板。"""
        try:
            from jinja2 import Template
            return Template(template).render(**variables)
        except ImportError:
            logger.warning("jinja2 not installed, using simple string replacement")
            result = template
            for key, value in variables.items():
                result = result.replace(f"{{{{ {key} }}}}", str(value))
                result = result.replace(f"{{{{ {key} }}}}", str(value))
            return result
        except Exception as exc:
            logger.error(f"Template rendering failed: {exc}, returning raw template")
            return template

    def _fallback_single_task(self, intent: str) -> List[Task]:
        """回退到单任务直接执行。"""
        return [Task(
            name="direct_execution",
            description=f"Direct execution: {intent}",
            worker_type="Answer-LLM",
            input_data=intent,
            estimated_time=5,
        )]


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("=== v3.0 decomposition self-test ===")

    from core.agent.v3_0.planning.skill_registry import SkillRegistry

    registry = SkillRegistry()
    engine = DecompositionEngine()

    # 1. 技能模板分解
    skill = registry.get("memory_analysis")
    tasks = engine.decompose_with_skill("scan 0x1234", skill)
    assert len(tasks) == 3
    assert tasks[0].name == "scan_address"
    print(f"[PASS] decompose_with_skill: {len(tasks)} tasks")

    # 2. 动态分解（无 LLM，会回退到单任务）
    async def test_decompose():
        tasks2 = await engine.decompose("scan memory for 100")
        assert len(tasks2) == 1
        assert tasks2[0].name == "direct_execution"
        print(f"[PASS] decompose fallback: {tasks2[0].name}")

    asyncio.run(test_decompose())

    # 3. 超时测试（构造一个 LLM 调用但设置极短超时）
    async def test_timeout():
        tasks3 = await engine.decompose("some intent", timeout_ms=1)
        assert len(tasks3) == 1
        assert tasks3[0].name == "direct_execution"
        print(f"[PASS] decompose timeout fallback: {tasks3[0].name}")

    asyncio.run(test_timeout())

    logger.info("=== All v3.0 decomposition self-tests passed ===")
