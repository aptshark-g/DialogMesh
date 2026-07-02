# -*- coding: utf-8 -*-
"""
core/agent/v3_0/planning/skill_registry.py
────────────────────────────────────────
DialogMesh Agent v3.0 — 技能注册中心（SkillRegistry）。

用途：
- 管理技能模板（SkillTemplate）的注册、查询、版本控制和生命周期。
- 支持按名称、标签、关键词、领域检索技能。
- 提供技能模板的 CRUD 操作和批量导入导出。

设计原则：
- 内存索引 + 可选持久化（SQLite/Redis），Phase 1 为内存实现。
- 线程安全：注册和查询使用锁保护。
- 防御性：重复注册时覆盖旧版本，并记录警告。

版本：3.0.0
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent.v3_0.planning.models import SkillLevel, SkillNotFoundError, SkillTemplate, SubtaskTemplate

logger = logging.getLogger(__name__)


class SkillRegistry:
    """技能注册中心 — 管理所有 SkillTemplate 的注册与查询。

    Args:
        auto_register_defaults: 是否自动注册默认的内置技能模板。
    """

    def __init__(self, auto_register_defaults: bool = True) -> None:
        self._skills: Dict[str, SkillTemplate] = {}
        self._lock = threading.RLock()
        self._version_history: Dict[str, List[str]] = {}
        if auto_register_defaults:
            self._register_builtin_skills()
        logger.info(f"SkillRegistry initialized (skills={len(self._skills)})")

    # ── 公共 API ─────────────────────────────────────────────────────────

    def register(self, skill: SkillTemplate) -> None:
        """注册或更新技能模板。

        如果同名技能已存在，旧版本会被覆盖，旧版本号记录到历史。
        """
        try:
            with self._lock:
                old = self._skills.get(skill.name)
                if old:
                    logger.warning(
                        f"Skill '{skill.name}' already exists (v{old.version}), "
                        f"overwriting with v{skill.version}"
                    )
                    self._version_history.setdefault(skill.name, []).append(old.version)
                self._skills[skill.name] = skill
                logger.info(f"Skill registered: {skill.name} (v{skill.version})")
        except Exception as exc:
            logger.error(f"Skill registration failed for {skill.name}: {exc}")
            raise

    def unregister(self, name: str) -> Optional[SkillTemplate]:
        """注销技能模板。"""
        try:
            with self._lock:
                skill = self._skills.pop(name, None)
                if skill:
                    logger.info(f"Skill unregistered: {name}")
                else:
                    logger.warning(f"Skill not found for unregister: {name}")
                return skill
        except Exception as exc:
            logger.error(f"Skill unregistration failed for {name}: {exc}")
            raise

    def get(self, name: str) -> SkillTemplate:
        """按名称获取技能模板。

        Raises:
            SkillNotFoundError: 技能不存在时抛出。
        """
        try:
            with self._lock:
                skill = self._skills.get(name)
                if skill is None:
                    raise SkillNotFoundError(f"Skill '{name}' not found in registry")
                return skill
        except SkillNotFoundError:
            raise
        except Exception as exc:
            logger.error(f"Skill retrieval failed for {name}: {exc}")
            raise

    def query(
        self,
        keyword: Optional[str] = None,
        tags: Optional[List[str]] = None,
        domain: Optional[str] = None,
    ) -> List[SkillTemplate]:
        """多维度查询技能模板。

        Args:
            keyword: 关键词（匹配 name/description/keywords）。
            tags: 标签列表（匹配任意一个）。
            domain: 领域标签。

        Returns:
            匹配的技能列表（按注册时间排序）。
        """
        try:
            with self._lock:
                results = []
                for skill in self._skills.values():
                    if keyword and not self._matches_keyword(skill, keyword):
                        continue
                    if tags and not any(t in skill.tags for t in tags):
                        continue
                    if domain and domain not in skill.domain_tags:
                        continue
                    results.append(skill)
                return results
        except Exception as exc:
            logger.error(f"Skill query failed: {exc}")
            return []

    def list_all(self) -> List[SkillTemplate]:
        """列出所有已注册技能。"""
        try:
            with self._lock:
                return list(self._skills.values())
        except Exception as exc:
            logger.error(f"Skill list_all failed: {exc}")
            return []

    def count(self) -> int:
        """获取已注册技能数量。"""
        try:
            with self._lock:
                return len(self._skills)
        except Exception as exc:
            logger.error(f"Skill count failed: {exc}")
            return 0

    def export_to_json(self, path: str) -> None:
        """导出所有技能到 JSON 文件。"""
        try:
            data = [s.to_dict() for s in self.list_all()]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Skills exported to {path} (count={len(data)})")
        except Exception as exc:
            logger.error(f"Skill export failed: {exc}")
            raise

    def import_from_json(self, path: str) -> int:
        """从 JSON 文件导入技能。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            imported = 0
            for item in data:
                subtasks = [
                    SkillTemplate.__dataclass_fields__["subtasks"].type(
                        name=s.get("name", ""),
                        description=s.get("description", ""),
                        worker_type=s.get("worker_type", "Planning-LLM"),
                        input_template=s.get("input_template", ""),
                        output_schema=s.get("output_schema", {}),
                        required=s.get("required", True),
                    )
                    for s in item.get("subtasks", [])
                ]
                level_raw = item.get("level", "STANDARD")
                try:
                    level = SkillLevel(level_raw) if isinstance(level_raw, str) else SkillLevel.STANDARD
                except ValueError:
                    logger.warning(f"Unknown skill level '{level_raw}', defaulting to STANDARD")
                    level = SkillLevel.STANDARD

                skill = SkillTemplate(
                    name=item.get("name", ""),
                    version=item.get("version", "1.0.0"),
                    description=item.get("description", ""),
                    keywords=item.get("keywords", []),
                    tags=item.get("tags", []),
                    domain_tags=item.get("domain_tags", []),
                    intent_categories=item.get("intent_categories", []),
                    primitives=item.get("primitives", []),
                    tool_hints=item.get("tool_hints", {}),
                    constraints=item.get("constraints", []),
                    level=level,
                    decomposition_pattern=item.get("decomposition_pattern", "sequential"),
                    subtasks=subtasks,
                    dependencies=item.get("dependencies", []),
                    timeout_seconds=item.get("timeout_seconds", 300.0),
                    fallback_skill=item.get("fallback_skill"),
                )
                self.register(skill)
                imported += 1
            logger.info(f"Skills imported from {path} (count={imported})")
            return imported
        except Exception as exc:
            logger.error(f"Skill import failed: {exc}")
            raise

    # ── 内部工具 ─────────────────────────────────────────────────────────

    def _matches_keyword(self, skill: SkillTemplate, keyword: str) -> bool:
        """检查技能是否匹配关键词。"""
        kw_lower = keyword.lower()
        if kw_lower in skill.name.lower():
            return True
        if kw_lower in skill.description.lower():
            return True
        return any(kw_lower in k.lower() for k in skill.keywords)

    def _register_builtin_skills(self) -> None:
        """注册内置的默认技能模板。"""
        try:
            # 内存分析技能
            memory_analysis = SkillTemplate(
                name="memory_analysis",
                description="Scan memory addresses, read values, and analyze call stacks",
                keywords=["memory", "scan", "address", "read", "value"],
                tags=["reverse_engineering", "memory"],
                domain_tags=["memory"],
                intent_categories=["scan_memory", "read_memory"],
                subtasks=[
                    SubtaskTemplate(
                        name="scan_address",
                        description="Scan target memory address",
                        worker_type="ToolExecutor",
                        input_template="{{ intent }}",
                    ),
                    SubtaskTemplate(
                        name="read_value",
                        description="Read value from memory",
                        worker_type="ToolExecutor",
                        input_template="address={{ address }}",
                    ),
                    SubtaskTemplate(
                        name="analyze_stack",
                        description="Analyze call stack information",
                        worker_type="Planning-LLM",
                        input_template="memory_context={{ context }}",
                    ),
                ],
            )
            self.register(memory_analysis)

            # 反汇编技能
            disassembly = SkillTemplate(
                name="disassembly",
                description="Disassemble a memory region and analyze instruction flow",
                keywords=["disassemble", "assembly", "instruction", "code"],
                tags=["reverse_engineering", "code_analysis"],
                domain_tags=["code"],
                intent_categories=["disassemble"],
                subtasks=[
                    SubtaskTemplate(
                        name="disassemble_region",
                        description="Disassemble memory region",
                        worker_type="ToolExecutor",
                        input_template="region={{ region }}",
                    ),
                    SubtaskTemplate(
                        name="analyze_flow",
                        description="Analyze control flow",
                        worker_type="Planning-LLM",
                        input_template="instructions={{ instructions }}",
                    ),
                ],
            )
            self.register(disassembly)

            logger.info(f"Builtin skills registered: {self.count()}")
        except Exception as exc:
            logger.error(f"Builtin skill registration failed: {exc}")
            raise


# ═══════════════════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    sys.path.insert(0, r"C:\Users\APTShark\PycharmProjects\DialogMesh")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("=== v3.0 skill_registry self-test ===")

    registry = SkillRegistry()
    assert registry.count() >= 2, "Builtin skills should be registered"

    skill = registry.get("memory_analysis")
    assert skill.name == "memory_analysis"
    print(f"[PASS] Get skill: {skill.name}")

    results = registry.query(keyword="memory")
    assert len(results) >= 1
    print(f"[PASS] Query keyword='memory': {len(results)} results")

    results_tag = registry.query(tags=["reverse_engineering"])
    assert len(results_tag) >= 2
    print(f"[PASS] Query tags: {len(results_tag)} results")

    try:
        registry.get("nonexistent")
        assert False, "Should raise SkillNotFoundError"
    except SkillNotFoundError:
        print("[PASS] SkillNotFoundError raised correctly")

    registry.unregister("memory_analysis")
    assert registry.count() >= 1
    print(f"[PASS] Unregister: count={registry.count()}")

    logger.info("=== All v3.0 skill_registry self-tests passed ===")
