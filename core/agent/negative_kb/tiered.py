"""TieredNegativeKB — 多层负知识库（keyword 快路径 → fuse 慢路径）.

2026-08-07 从 v4/un_use 恢复（UN_USE_AUDIT 高价值断线候选）:
  - 原依赖 core.agent.v4.tiered.pipeline（已删）→ 改为自包含两层
  - 底层 core.agent.negative_kb（活跃）: RuleStore + FuseController
  - 接入 executor 工具调用前校验（负知识约束, 与权限引擎互补）

Tier 0 (keyword): RuleStore pattern 匹配, 亚毫秒, 高置信直返
Tier 1 (fuse):    FuseController hit 跟踪 + learned overrides
"""

from __future__ import annotations

import logging

from .negative_kb import NegativeKB
from .models import NegativeLevel, NegativeResult, ContextualNegativeRule

logger = logging.getLogger(__name__)


# 种子规则（初始负知识约束; HARD_BLOCK 需 verified）
SEED_RULES = [
    ContextualNegativeRule(
        rule_id="neg_shell_force_delete", level=NegativeLevel.HARD_BLOCK,
        message="禁止强制删除/覆盖关键路径（rm -rf / chmod 777 等危险操作）",
        domain="engineering", is_verified=True,
        keywords=["rm -rf", "rm -fr", "chmod 777", "chmod 666", "del /s", "rd /s"],
    ),
    ContextualNegativeRule(
        rule_id="neg_secret_inline", level=NegativeLevel.HARD_BLOCK,
        message="禁止在代码/配置中硬编码密钥或令牌",
        domain="engineering", is_verified=True,
        keywords=["api_key", "secret_key", "password=", "token=", "api-key"],
    ),
    ContextualNegativeRule(
        rule_id="neg_permission_escalate", level=NegativeLevel.WARN,
        message="权限提升操作需审批（sudo 无约束/提权）",
        domain="engineering",
        keywords=["sudo ", "runas ", "setcap"],
    ),
]


class TieredNegativeKB:
    """多层负知识库: keyword 快路径 + fuse 慢路径。"""

    def __init__(self, store=None):
        self._kb = NegativeKB(store=store)
        self._keyword_hits = 0
        self._fuse_hits = 0

    def check(self, ctx: str = "") -> NegativeResult:
        """两层检查: 先 keyword 快路径（高置信直返）, 再 fuse 慢路径。"""
        if not ctx:
            return NegativeResult()
        # Tier 0: keyword 快路径（HARD_BLOCK 已验证规则 → 直返拦截）
        level = self._kb.store.get_highest(ctx)
        if level == NegativeLevel.HARD_BLOCK:
            for rule in self._kb.store.applicable(ctx):
                if rule.level == NegativeLevel.HARD_BLOCK and rule.is_verified:
                    self._keyword_hits += 1
                    return NegativeResult(
                        NegativeLevel.HARD_BLOCK, rule.rule_id,
                        rule.message, blocked=True)
        # Tier 1: fuse 慢路径（WARN/SOFT_DISCOURAGE / 未验证 HARD_BLOCK 降级）
        result = self._kb.check(ctx)
        # FuseController 原始语义 WARN 首次命中 blocked=True（设计瑕疵）—
        # tiered 层修正: WARN/SOFT_DISCOURAGE 只提醒, 不拦截
        if result.level in (NegativeLevel.WARN, NegativeLevel.SOFT_DISCOURAGE):
            result.blocked = False
        self._fuse_hits += 1
        return result

    def register(self, rule: ContextualNegativeRule) -> None:
        """注册规则（HARD_BLOCK 未验证 → NegativeKB 拒绝）."""
        self._kb.register(rule)

    def stats(self) -> dict:
        return {
            "keyword_hits": self._keyword_hits,
            "fuse_hits": self._fuse_hits,
            "rules": len(self._kb.store.rules),
        }
