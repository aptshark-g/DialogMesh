"""CLI health check / doctor command."""
from __future__ import annotations
import os, sys


def _health_check(engine):
    """Run comprehensive health check."""
    checks = []
    all_ok = True

    # 1. Module importability
    modules = [
        ("v4/observation_compiler", "core.agent.v4.observation_compiler.models"),
        ("v4/hypothesis_engine", "core.agent.v4.hypothesis_engine.models"),
        ("v4/skill_layer", "core.agent.v4.skill_layer.models"),
        ("v4/world", "core.agent.v4.world.schema"),
        ("v4/context", "core.agent.v4.context.cross_domain_ir"),
        ("v4/tiered", "core.agent.v4.tiered.pipeline"),
        ("v4/persistence", "core.agent.v4.persistence.unified_store"),
        ("v4/runtime", "core.agent.v4.runtime.engine"),
        ("tree_sitter", "tree_sitter"),
        ("networkx", "networkx"),
        ("numpy", "numpy"),
    ]
    for name, mod_path in modules:
        try:
            __import__(mod_path)
            checks.append(("PASS", "Module", name))
        except ImportError as e:
            checks.append(("FAIL", "Module", f"{name}: {e}"))
            all_ok = False

    # 2. SQLite database
    try:
        from core.agent.v4.persistence.unified_store import UnifiedGraphStore
        store = UnifiedGraphStore("data/dialogmesh.db")
        store.open()
        stats = store.stats
        store.close()
        checks.append(("PASS", "Database",
                       f"data/dialogmesh.db ({stats['node_count']} nodes, {stats['edge_count']} edges)"))
    except Exception as e:
        checks.append(("FAIL", "Database", str(e)))
        all_ok = False

    # 3. Runtime engine
    if engine is not None:
        checks.append(("PASS", "Runtime", f"{engine.adapter_count} adapters active"))
    else:
        checks.append(("INFO", "Runtime", "not started"))

    # 4. Disk space
    data_dir = "data"
    if os.path.isdir(data_dir):
        total_size = sum(
            os.path.getsize(os.path.join(dirpath, f))
            for dirpath, _, filenames in os.walk(data_dir)
            for f in filenames
        )
        checks.append(("PASS", "Disk", f"data/ = {total_size / 1024:.1f} KB"))
    else:
        checks.append(("INFO", "Disk", "data/ directory not found"))

    # Print results
    print(f"{'Status':<6s} {'Check':<10s} {'Detail'}")
    print("-" * 60)
    for status, check, detail in checks:
        print(f"{status:<6s} {check:<10s} {detail}")

    if all_ok:
        print(f"\nAll checks passed")
    else:
        print(f"\nSome checks FAILED")

    return 0 if all_ok else 1
