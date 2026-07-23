"""Zone Strategy — data-driven routing decisions. No hardcoded zone names.

Each zone defines: skip_chains, execution_mode, prompt_style, llm_temperature.
Trigger conditions consume this config, not hardcoded if/elif.
"""

ZONE_STRATEGY = {
    "ATOMIC": {
        "skip_chains": ["intent", "planning", "profile"],
        "execution_mode": "cache",
        "prompt_style": "concise",
        "temperature": 0.1,
        "max_tokens": 512,
    },
    "PSYCHE": {
        "skip_chains": ["intent", "planning"],
        "execution_mode": "small_model",
        "prompt_style": "empathetic",
        "temperature": 0.7,
        "max_tokens": 1024,
    },
    "EXPLORE": {
        "skip_chains": ["planning", "profile"],
        "execution_mode": "retrieval",
        "prompt_style": "socratic",
        "temperature": 0.5,
        "max_tokens": 2048,
    },
    "PRECISION": {
        "skip_chains": ["profile"],
        "execution_mode": "cot",
        "prompt_style": "analytical",
        "temperature": 0.2,
        "max_tokens": 4096,
    },
    "ABYSS": {
        "skip_chains": ["profile"],
        "execution_mode": "react",
        "prompt_style": "exhaustive",
        "temperature": 0.3,
        "max_tokens": 8192,
    },
    "MIXED": {
        "skip_chains": ["planning", "profile"],
        "execution_mode": "slow",
        "prompt_style": "default",
        "temperature": 0.4,
        "max_tokens": 2048,
    },
}


def should_skip_chain(zone: str, chain_name: str) -> bool:
    """Check if a chain should be skipped for this zone."""
    strategy = ZONE_STRATEGY.get(zone, ZONE_STRATEGY["MIXED"])
    return chain_name in strategy.get("skip_chains", [])


def get_zone_config(zone: str) -> dict:
    """Get full config for a zone. Defaults to MIXED."""
    return ZONE_STRATEGY.get(zone, ZONE_STRATEGY["MIXED"])
