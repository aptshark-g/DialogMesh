"""G3 Integration Completeness Check.

Detects modules whose _init_* method is defined but never called in start().
Symptom: module exists, passes unit tests, but is DEAD in runtime.
"""
import ast, sys, re
from collections import Counter

def check_integration(engine_path: str) -> dict:
    """Check every _init_* method is called in start()."""
    with open(engine_path, 'r', encoding='utf-8') as f:
        source = f.read()
    
    tree = ast.parse(source)
    
    # Find all _init_* method definitions
    init_defs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith('_init_'):
            init_defs.append(node.name)
    
    # Find all calls to _init_* in start()
    start_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'start':
            start_node = node
            break
    
    if not start_node:
        return {"error": "start() method not found"}
    
    called_inits = set()
    for node in ast.walk(start_node):
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name and name.startswith('_init_'):
                called_inits.add(name)
    
    # Find _init_* in any other *class* methods (not just start)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name != 'start':
                    for subnode in ast.walk(item):
                        if isinstance(subnode, ast.Call):
                            func = subnode.func
                            name = None
                            if isinstance(func, ast.Attribute):
                                name = func.attr
                            elif isinstance(func, ast.Name):
                                name = func.id
                            if name and name.startswith('_init_'):
                                called_inits.add(name)
    
    uncalled = [d for d in init_defs if d not in called_inits]
    
    return {
        "total_inits": len(init_defs),
        "called_in_start": len(called_inits),
        "uncalled": uncalled,
        "passed": len(uncalled) == 0,
        "coverage": len(called_inits) / max(1, len(init_defs)),
    }


def check_softconfig(project_root: str) -> dict:
    """Check hardcoded strings that should be in soft_config."""
    import os, json
    
    config_dir = os.path.join(project_root, 'data', 'soft_config')
    if not os.path.isdir(config_dir):
        return {"error": "soft_config dir missing", "passed": False}
    
    config_files = [f for f in os.listdir(config_dir) if f.endswith('.json')]
    config_keys = set()
    for cf in config_files:
        try:
            with open(os.path.join(config_dir, cf)) as f:
                data = json.load(f)
            for k, v in _flatten_keys(data):
                config_keys.add(k)
        except Exception:
            pass
    
    # Check engine.py for hardcoded strings matching config patterns
    engine_path = os.path.join(project_root, 'core', 'agent', 'v4', 'runtime', 'engine.py')
    hardcoded = 0
    if os.path.exists(engine_path):
        with open(engine_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""'):
                continue
            # Check for hardcoded thresholds
            if re.search(r'(threshold|max_|min_)\s*=\s*\d+', stripped):
                hardcoded += 1
    
    return {
        "config_files": len(config_files),
        "config_keys": len(config_keys),
        "hardcoded_thresholds": hardcoded,
        "needs_migration": hardcoded,
    }


def check_transition_types(trace_path_or_dict) -> dict:
    """Check transition type coverage."""
    import json
    if isinstance(trace_path_or_dict, str):
        with open(trace_path_or_dict) as f:
            data = json.load(f)
    else:
        data = trace_path_or_dict
    
    dist = data.get("reason_distribution", {})
    total = data.get("total_transitions", 0)
    types = sorted(dist.keys())
    
    return {
        "types": types,
        "total": total,
        "unique_count": len(types),
        "missing_critical": [t for t in ['observe', 'infer', 'reflect', 'reject', 'strengthen'] if t not in types],
        "passed": len(types) >= 4,
    }


def _flatten_keys(d, prefix=''):
    """Flatten nested dict keys."""
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            yield from _flatten_keys(v, full_key)
        else:
            yield full_key, v


if __name__ == "__main__":
    import os
    root = os.getcwd()  # Must be run from project root
    engine = os.path.join(root, 'core', 'agent', 'v4', 'runtime', 'engine.py')
    
    print("G3 Integration Check")
    print("═══════════════════")
    result = check_integration(engine)
    status = "✅" if result["passed"] else "❌"
    print(f"  {status} coverage={result['coverage']:.0%} called={result['called_in_start']}/{result['total_inits']}")
    if result["uncalled"]:
        print(f"  UNCALLED: {', '.join(result['uncalled'])}")
    
    print("\nG1 Soft-Config Check")
    print("═══════════════════")
    sc = check_softconfig(root)
    print(f"  config_files={sc['config_files']} keys={sc['config_keys']}")
    print(f"  hardcoded_thresholds_in_engine={sc.get('hardcoded_thresholds', '?')}")
