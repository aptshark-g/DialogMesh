"""DialogMesh v6 CLI — unified command interface.

Commands:
  chat       Interactive conversation with full persistence
  test       Run benchmark suite
  ab         A/B comparison (CoT+BFI vs baseline)
  profile    View/reset persistent OCEAN profile
  monitor    View session logs and summaries
  export     Export session data as JSON/CSV
  config     Show current configuration
  clean      Reset persistence data

Data produced per session:
  data/monitor/chat_<ts>.jsonl         — per-turn full state
  data/monitor/chat_<ts>_profile.json  — TrackB tags
  data/monitor/chat_<ts>_summary.json  — final analysis
  data/profile/ocean_profile.json      — cross-session OCEAN
  data/neuro_symbolic_rules.json       — learned rules
  data/mind_*.json                     — Mind relations/anchors/mistakes
"""
import sys, os, json, argparse, subprocess, time

sys.path.insert(0, '.')


def _get_python():
    return sys.executable


def cmd_chat(args):
    """Interactive chat session."""
    from core.agent.v4.cognitive.tests.chat_mbti_test import run_chat_test
    run_chat_test(args.turns or 10)


def cmd_test(args):
    """Run benchmarks."""
    benches = {
        "live": "core/agent/v4/cognitive/tests/bench_live.py",
        "controlled": "core/agent/v4/cognitive/tests/bench_controlled.py",
        "implicit": "core/agent/v4/cognitive/tests/bench_implicit.py",
        "monitored": "core/agent/v4/cognitive/tests/bench_monitored.py",
    }
    if args.bench == "all":
        targets = list(benches.values())
    else:
        targets = [benches[args.bench]]

    for t in targets:
        print(f"\n=== {os.path.basename(t)} ===")
        subprocess.run([_get_python(), t], env={**os.environ, "PYTHONHOME": "", "PYTHONPATH": ""})


def cmd_ab(args):
    """A/B comparison."""
    subprocess.run([_get_python(), "core/agent/v4/cognitive/tests/bench_ab_ocean.py"],
                   env={**os.environ, "PYTHONHOME": "", "PYTHONPATH": ""})


def cmd_profile(args):
    """View/reset OCEAN profile."""
    path = "data/profile/ocean_profile.json"
    if args.reset:
        if os.path.exists(path):
            os.remove(path)
            print("Profile reset.")
        return
    if not os.path.exists(path):
        print("No profile yet. Run 'chat' first.")
        return
    with open(path) as f:
        data = json.load(f)
    print(f"OCEAN Profile — {data.get('turn_count',0)} turns — MBTI≈{data.get('mbti_approx','?')}")
    dims = data.get("dims", {})
    for k, v in sorted(dims.items(), key=lambda x: abs(x[1] - 0.5), reverse=True)[:6]:
        bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
        print(f"  {k}: {v:.2f} {bar}")


def cmd_monitor(args):
    """View session logs."""
    d = "data/monitor"
    if not os.path.exists(d):
        print("No monitor data.")
        return
    files = sorted([f for f in os.listdir(d) if f.startswith("chat_") and f.endswith(".jsonl")], reverse=True)
    if args.list:
        for f in files[:15]:
            sz = os.path.getsize(os.path.join(d, f))
            print(f"  {f}  ({sz}B)")
        return
    if files:
        path = os.path.join(d, files[0])
        with open(path) as f:
            lines = f.readlines()
        print(f"Latest: {files[0]} — {len(lines)} turns")
        for line in lines[-5:]:
            d2 = json.loads(line)
            print(f"  T{d2['turn']}: S={d2.get('trace_S',0)} W={d2.get('trace_W',0)} "
                  f"ocean={d2.get('ocean_mbti','?')}")
    else:
        print("No sessions yet.")


def cmd_export(args):
    """Export session data."""
    d = "data/monitor"
    files = sorted([f for f in os.listdir(d) if f.startswith("chat_") and f.endswith(".jsonl")], reverse=True)
    if not files:
        print("No sessions to export.")
        return
    path = os.path.join(d, files[0])
    with open(path) as f:
        rows = [json.loads(line) for line in f]

    if args.format == "csv":
        out = "ocean_dims,trace_S,trace_W,ocean_mbti\n"
        for r in rows:
            od = r.get("ocean_dims", {})
            dims_str = ";".join(f"{k}={v}" for k, v in od.items())
            out += f'"{dims_str}",{r.get("trace_S",0)},{r.get("trace_W",0)},{r.get("ocean_mbti","?")}\n'
        out_path = args.output or "export.csv"
        with open(out_path, "w") as f:
            f.write(out)
    else:
        out_path = args.output or "export.json"
        with open(out_path, "w") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    print(f"Exported {len(rows)} rows → {out_path}")


def cmd_config(args):
    """Show configuration."""
    paths = {
        "OCEAN profile": os.path.exists("data/profile/ocean_profile.json"),
        "ABC rules": os.path.exists("data/neuro_symbolic_rules.json"),
        "Mind relations": os.path.exists("data/mind_relation.json"),
        "Annotations": os.path.exists("data/annotations/"),
        "Monitor sessions": len([f for f in os.listdir("data/monitor") if f.endswith(".jsonl")]) if os.path.exists("data/monitor") else 0,
    }
    print("DialogMesh v6 Configuration")
    print("=" * 40)
    for k, v in paths.items():
        print(f"  {k}: {v}")
    print(f"\n  Python: {_get_python()}")
    print(f"  CWD: {os.getcwd()}")


def cmd_clean(args):
    """Reset persistence."""
    files = ["data/profile/ocean_profile.json", "data/neuro_symbolic_rules.json",
             "data/mind_relation.json", "data/mind_attention.json", "data/mind_mistakes.json"]
    count = 0
    for f in files:
        if os.path.isfile(f):
            os.remove(f); count += 1
    if args.all:
        import shutil
        for d in ["data/annotations", "data/monitor"]:
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True); count += 1
    print(f"Cleaned {count} items.")


def main():
    parser = argparse.ArgumentParser(description="DialogMesh v6 CLI")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("chat", help="Interactive chat with full persistence")
    p.add_argument("--turns", type=int, default=10)

    p = sub.add_parser("test", help="Run benchmarks")
    p.add_argument("bench", nargs="?", default="all", choices=["all", "live", "controlled", "implicit", "monitored"])

    sub.add_parser("ab", help="A/B comparison test (CoT+BFI vs baseline)")

    p = sub.add_parser("profile", help="View/reset OCEAN profile")
    p.add_argument("--reset", action="store_true")

    p = sub.add_parser("monitor", help="View session logs")
    p.add_argument("--list", action="store_true", help="List all sessions")

    p = sub.add_parser("export", help="Export session data")
    p.add_argument("--format", choices=["json", "csv"], default="json")
    p.add_argument("--output", help="Output file path")

    sub.add_parser("config", help="Show configuration")

    p = sub.add_parser("clean", help="Reset persistence")
    p.add_argument("--all", action="store_true", help="Also clean annotations and logs")

    args = parser.parse_args()
    cmds = {"chat": cmd_chat, "test": cmd_test, "ab": cmd_ab, "profile": cmd_profile,
            "monitor": cmd_monitor, "export": cmd_export, "config": cmd_config, "clean": cmd_clean}
    fn = cmds.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
