"""CLI configuration management commands."""
from __future__ import annotations


def _config_show(engine):
    """Show current configuration."""
    try:
        from core.agent.v4.world.params import WorldParams
        p = WorldParams()
        print("WorldParams (v4):")
        for fld in sorted(dir(p)):
            if fld.startswith('_') or callable(getattr(p, fld)):
                continue
            val = getattr(p, fld)
            if isinstance(val, dict):
                print(f"  {fld}:")
                for k, v in val.items():
                    print(f"    {k}: {v}")
            elif isinstance(val, list):
                print(f"  {fld}: [{len(val)} items]")
            else:
                print(f"  {fld}: {val}")

        # Show runtime.yaml config if available
        import pathlib
        config_path = pathlib.Path("config/runtime.yaml")
        if config_path.exists():
            import yaml
            raw = yaml.safe_load(config_path.read_text())
            print(f"\nruntime.yaml:")
            for path_name, modules in raw.get("paths", {}).items():
                print(f"  {path_name}: {len(modules)} modules")
                for m in modules:
                    print(f"    - {m['name']} (timeout={m.get('timeout_ms', '?')}ms)")
        return 0
    except Exception as e:
        print(f"Config error: {e}")
        return 1


def _config_set(engine, key: str, value: str):
    """Set a configuration value."""
    try:
        from core.agent.v4.world.params import WorldParams, get_world_params
        p = get_world_params({key: _parse_value(value)})
        print(f"Set {key} = {value} (runtime session only)")
        print("  Note: permanent changes require editing config/runtime.yaml")
        return 0
    except Exception as e:
        print(f"Config set error: {e}")
        return 1


def _parse_value(val: str):
    """Parse string value to appropriate type."""
    if val.lower() in ("true", "yes"):
        return True
    if val.lower() in ("false", "no"):
        return False
    try:
        return int(val)
    except ValueError:
        try:
            return float(val)
        except ValueError:
            return val
