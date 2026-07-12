"""Executor mapping: abstract action -> concrete tool commands."""
from typing import Dict, Optional

EXECUTOR_MAP: Dict[str, Dict[str, str]] = {
    "create_module": {"shell": "mkdir -p {name}", "codex": "create_module({name})", "agent": "agent.create_module({name})", "default": "Create module: {name}"},
    "register_module": {"shell": "echo register {name}", "codex": "register_module({name})", "agent": "agent.register({name})", "default": "Register: {name}"},
    "run_test": {"shell": "pytest {target}", "codex": "run_test({target})", "agent": "agent.test({target})", "default": "Run tests: {target}"},
    "update_config": {"shell": "echo update", "codex": "update_config({key},{value})", "agent": "agent.update_config({key},{value})", "default": "Update config {key}={value}"},
    "add_dependency": {"shell": "pip install {pkg}", "codex": "add_dependency({pkg})", "agent": "agent.install({pkg})", "default": "Add dependency: {pkg}"},
    "generate_code": {"shell": "echo generate", "codex": "generate({template})", "agent": "agent.generate({template})", "default": "Generate from: {template}"},
    "verify_health": {"shell": "curl {endpoint}", "codex": "health_check({endpoint})", "agent": "agent.health_check({endpoint})", "default": "Health: {endpoint}"},
    "verify_metrics": {"shell": "curl {endpoint}/metrics", "codex": "check_metrics({endpoint})", "agent": "agent.check_metrics({endpoint})", "default": "Metrics: {endpoint}"},
}

def resolve_executor(action: str, executor: str = "default", params: dict = None) -> Optional[str]:
    mapping = EXECUTOR_MAP.get(action)
    if not mapping: return None
    template = mapping.get(executor, mapping.get("default"))
    if template and params:
        try: return template.format(**params)
        except KeyError: pass
    return template
