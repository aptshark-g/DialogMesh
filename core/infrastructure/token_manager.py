# core/infrastructure/token_manager.py
"""TokenManager — LLM 上下文长度计算与智能截断。

设计原则：
- 精确计数：优先 tiktoken，回退到字符数 × 修正系数（中文 1:2 英文 1:0.5）
- 预留空间：总上下文 = 系统提示 + 历史 + 用户查询 + 预留回复
- 智能截断：按优先级滑动（保留高优先级，丢弃低优先级 oldest）
- 适配性：支持不同 LLM 的上下文窗口（默认 8K，可配置）

使用方式：
    from core.infrastructure.token_manager import TokenManager

    tm = TokenManager(model_name="deepseek-v4-pro", max_tokens=8192)
    
    # 计算 token
    n = tm.count("帮我写 Python 代码")
    
    # 截断上下文
    context_blocks = [
        {"role": "system", "content": "你是助手...", "priority": 10},
        {"role": "user", "content": "T0: 帮我写 Python...", "priority": 5},
        {"role": "user", "content": "T1: 怎么优化...", "priority": 5},
    ]
    fitted = tm.fit_context(context_blocks, reserve_for_reply=1024)
    # → 自动截断 oldest 低优先级 block，确保总 token <= 8192-1024
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 模型上下文窗口配置
MODEL_CONTEXT_LIMITS = {
    # OpenAI
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16385,
    # DeepSeek
    "deepseek-v4-pro": 64000,
    "deepseek-v4-flash": 64000,
    "deepseek-reasoner": 64000,
    "deepseek-chat": 64000,
    # Moonshot
    "kimi-k2-0714-preview": 256000,
    # 通用默认值
    "default": 8192,
}

# 中文 token 修正系数（中文字符 ≈ 1.5-2.5 tokens）
# 基于经验：OpenAI 的 cl100k_base 编码中，中文字符平均 1.5-2 tokens
CHINESE_TOKEN_RATIO = 2.0
ENGLISH_TOKEN_RATIO = 0.5  # 英文单词平均 1.3 tokens，但这里按字符算


class TokenManager:
    """Token 计数与上下文截断管理器。"""

    def __init__(self, model_name: str = "default", max_tokens: Optional[int] = None):
        self.model_name = model_name
        self.max_tokens = max_tokens or MODEL_CONTEXT_LIMITS.get(model_name, MODEL_CONTEXT_LIMITS["default"])
        self._encoder = None
        self._encoder_type = None
        self._init_encoder()

    def _init_encoder(self):
        """初始化 token 编码器（优先 tiktoken，回退到 transformers）"""
        # 尝试 tiktoken
        try:
            import tiktoken
            # 尝试匹配模型编码器
            enc_name = self._map_to_tiktoken_encoding(self.model_name)
            self._encoder = tiktoken.get_encoding(enc_name)
            self._encoder_type = "tiktoken"
            logger.info(f"TokenManager using tiktoken ({enc_name})")
            return
        except Exception:
            pass

        # 回退：使用 transformers tokenizer（如果可用）
        try:
            from transformers import AutoTokenizer
            # 使用 BGE 的 tokenizer 作为近似（中文支持好）
            self._encoder = AutoTokenizer.from_pretrained(
                "BAAI/bge-small-zh",
                local_files_only=True,
                use_fast=True,
            )
            self._encoder_type = "transformers"
            logger.info("TokenManager using transformers tokenizer")
            return
        except Exception:
            pass

        # 最终回退：字符计数 + 经验修正
        self._encoder_type = "approximation"
        logger.warning("TokenManager falling back to character-count approximation")

    def _map_to_tiktoken_encoding(self, model_name: str) -> str:
        """将模型名映射到 tiktoken 编码器名称。"""
        if model_name.startswith("gpt-4") or model_name.startswith("gpt-3.5"):
            return "cl100k_base"
        # DeepSeek 使用与 GPT-4 相同的编码
        if model_name.startswith("deepseek"):
            return "cl100k_base"
        # 默认
        return "cl100k_base"

    # ── 核心计数 ───────────────────────────────────────────────

    def count(self, text: str) -> int:
        """计算文本的 token 数量。"""
        if not text:
            return 0

        if self._encoder_type == "tiktoken":
            return len(self._encoder.encode(text))

        if self._encoder_type == "transformers":
            return len(self._encoder.encode(text, add_special_tokens=False))

        # 回退：字符计数 + 经验修正
        return self._approximate_count(text)

    def count_messages(self, messages: List[Dict[str, str]]) -> int:
        """计算消息列表的总 token 数（含 OpenAI 格式开销）。"""
        total = 0
        for msg in messages:
            # 每条消息的开销：~4 tokens (role + content 包装)
            total += 4
            total += self.count(msg.get("content", ""))
            if msg.get("name"):
                total += self.count(msg["name"])
        # 初始开销
        total += 3
        return total

    def _approximate_count(self, text: str) -> int:
        """字符计数近似：中文字符 × 2.0 + 英文/数字字符 × 0.5。"""
        import re
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * CHINESE_TOKEN_RATIO + other_chars * ENGLISH_TOKEN_RATIO)

    # ── 上下文截断 ─────────────────────────────────────────────

    def fit_context(self, blocks: List[Dict[str, Any]], reserve_for_reply: int = 1024) -> List[Dict[str, Any]]:
        """智能截断上下文块，确保总 token <= max_tokens - reserve_for_reply。

        策略：
        1. 按 priority 排序（高优先保留）
        2. 同 priority 按 age 排序（新的保留，old 丢弃）
        3. 从低优先级 oldest 开始丢弃，直到满足预算

        Args:
            blocks: 每个块至少包含 {"content": str, "priority": int, "age": int}
            reserve_for_reply: 为 LLM 回复预留的 token 数

        Returns:
            截断后的块列表（保持原始顺序）
        """
        budget = self.max_tokens - reserve_for_reply
        if budget <= 0:
            return []

        # 计算每个块的 token
        for block in blocks:
            block["_token"] = self.count(block.get("content", ""))

        total = sum(b.get("_token", 0) for b in blocks)
        if total <= budget:
            return blocks

        # 需要截断：按 (priority, -age) 排序，低优先级且 oldest 的先丢弃
        sorted_blocks = sorted(blocks, key=lambda b: (b.get("priority", 0), -b.get("age", 0)))

        # 从低到高丢弃，直到预算内
        remaining = list(blocks)  # 保持原始顺序
        current_total = total

        for block in sorted_blocks:
            if current_total <= budget:
                break
            if block in remaining:
                remaining.remove(block)
                current_total -= block.get("_token", 0)
                logger.debug(f"Context truncated: removed block with priority={block.get('priority')}, tokens={block.get('_token')}")

        # 清理临时字段
        for b in blocks:
            b.pop("_token", None)

        return remaining

    def fit_messages(self, messages: List[Dict[str, str]], reserve_for_reply: int = 1024) -> List[Dict[str, str]]:
        """针对 OpenAI 格式的消息截断。

        策略：
        - 系统消息（role=system）最高优先级，永不丢弃
        - 用户消息按时间倒序保留（最新的优先）
        - 超出预算时丢弃 oldest user 消息
        """
        budget = self.max_tokens - reserve_for_reply
        if budget <= 0:
            return [msg for msg in messages if msg.get("role") == "system"]

        # 分离系统消息
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        system_tokens = self.count_messages(system_msgs)
        available = budget - system_tokens

        if available <= 0:
            return system_msgs

        # 从 newest 开始累加，直到预算满
        # other_msgs 假设是时间顺序，保留 suffix（最新的）
        kept = []
        used = 0
        for msg in reversed(other_msgs):
            msg_tokens = self.count(msg.get("content", "")) + 4  # 开销
            if used + msg_tokens <= available:
                kept.insert(0, msg)
                used += msg_tokens
            else:
                break

        return system_msgs + kept

    def truncate_text(self, text: str, max_tokens: int, ellipsis: str = "...") -> str:
        """截断文本到指定 token 数。"""
        if self.count(text) <= max_tokens:
            return text

        # 二分查找截断点
        low, high = 0, len(text)
        while low < high:
            mid = (low + high) // 2
            truncated = text[:mid] + ellipsis
            if self.count(truncated) <= max_tokens:
                low = mid + 1
            else:
                high = mid

        # 回退一点确保不超限
        result = text[:low - 1] + ellipsis
        return result

    # ── 状态 ───────────────────────────────────────────────────

    def get_info(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "max_tokens": self.max_tokens,
            "encoder_type": self._encoder_type,
            "reserve_for_reply": 1024,
        }


# 便捷函数：全局默认实例
def get_token_manager(model_name: str = "default") -> TokenManager:
    """获取默认 TokenManager。"""
    return TokenManager(model_name=model_name)


def count_tokens(text: str, model_name: str = "default") -> int:
    """快捷计数函数。"""
    return get_token_manager(model_name).count(text)
