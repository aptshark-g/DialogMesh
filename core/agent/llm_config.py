"""LLM call configuration — single source of truth for token limits and temperatures."""

from dataclasses import dataclass


@dataclass
class LLMCallConfig:
    """LLM call parameters. Loaded from config, with sensible defaults."""
    max_tokens: int = 300
    temperature: float = 0.1
    
    # Task-specific overrides
    diverge_temperature: float = 0.8
    converge_temperature: float = 0.1
    verify_max_tokens: int = 150
    compress_max_tokens: int = 100
    explain_max_tokens: int = 150
    discover_max_tokens: int = 300
    suggest_max_tokens: int = 100
    synthesis_max_tokens: int = 300


# Default instance
DEFAULT = LLMCallConfig()


def load_from_config() -> LLMCallConfig:
    """Load LLM call config from project config file."""
    try:
        import json
        cfg = json.loads(open("config/l2_config.json", encoding='utf-8').read())
        llm_cfg = cfg.get("llm_call", {})
        return LLMCallConfig(
            max_tokens=llm_cfg.get("max_tokens", 300),
            temperature=llm_cfg.get("temperature", 0.1),
            diverge_temperature=llm_cfg.get("diverge_temperature", 0.8),
            converge_temperature=llm_cfg.get("converge_temperature", 0.1),
            verify_max_tokens=llm_cfg.get("verify_max_tokens", 150),
            compress_max_tokens=llm_cfg.get("compress_max_tokens", 100),
            explain_max_tokens=llm_cfg.get("explain_max_tokens", 150),
            discover_max_tokens=llm_cfg.get("discover_max_tokens", 300),
            suggest_max_tokens=llm_cfg.get("suggest_max_tokens", 100),
            synthesis_max_tokens=llm_cfg.get("synthesis_max_tokens", 300),
        )
    except Exception:
        return DEFAULT
