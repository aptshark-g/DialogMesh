"""DialogMesh v6 CLI — unified command interface.

Usage:
  python -m core.agent.v4.cli <command> [options]

Commands:
  chat          Interactive conversation with profile tracking
  test          Run benchmark suite
  ab            A/B comparison test
  profile       View/manage persistent profile
  monitor       View session logs
  clean         Reset persistence data
"""
import sys, os, json, argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


def cmd_chat(args):
    """Interactive chat session with full persistence."""
    from core.agent.v4.cognitive.tests.chat_mbti_test import run_chat_test
    turns = args.turns or 10
    run_chat_test(turns)


def cmd_test(args):
    """Run benchmark suite."""
    if args.bench == "all":
        print("Running full benchmark suite...")
        modules = ["bench_live", "bench_controlled", "bench_implicit", "bench_monitored"]
    else:
        modules = [args.bench]
    
    for mod in modules:
        print(f"\n=== {mod} ===")
        os.system(f"{sys.executable} -m core.agent.v4.cognitive.tests.{mod}")


def cmd_ab(args):
    """A/B comparison test."""
    from core.agent.v4.cognitive.tests.bench_ab_ocean import run_ab
    run_ab() if hasattr(sys.modules.get('bench_ab_ocean', object()), 'run_ab') else \
        os.system(f"{sys.executable} core/agent/v4/cognitive/tests/bench_ab_ocean.py")


def cmd_profile(args):
    """View or reset persistent profile."""
    path = "data/profile/ocean_profile.json"
    if args.reset:
        if os.path.exists(path):
            os.remove(path)
        print("Profile reset — will start fresh next session")
        return
    
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        print(f"OCEAN Profile ({data.get('turn_count', 0)} turns, MBTI≈{data.get('mbti_approx', '?')})")
        dims = data.get("dims", {})
        for k, v in sorted(dims.items(), key=lambda x: abs(x[1]-0.5), reverse=True):
            bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
            print(f"  {k}: {v:.2f} {bar}")
    else:
        print("No profile yet — run 'chat' first")


def cmd_monitor(args):
    """View session logs."""
    log_dir = "data/monitor"
    if not os.path.exists(log_dir):
        print("No monitor data")
        return
    
    files = sorted([f for f in os.listdir(log_dir) if f.startswith("chat_") and f.endswith(".jsonl")],
                   reverse=True)
    
    if args.list:
        for f in files[:10]:
            path = os.path.join(log_dir, f)
            size = os.path.getsize(path)
            print(f"  {f} ({size}B)")
        return
    
    if args.last and files:
        path = os.path.join(log_dir, files[0])
        if args.last.endswith("jsonl"):
            with open(path) as f:
                lines = f.readlines()
            print(f"Session: {files[0]} ({len(lines)} turns)")
            for line in lines[-3:]:
                d = json.loads(line)
                print(f"  T{d['turn']}: S={d.get('trace_S',0)} W={d.get('trace_W',0)} "
                      f"ocean={d.get('ocean_mbti','?')}")
        elif args.last == "summary":
            summary_path = path.replace(".jsonl", "_summary.json")
            if os.path.exists(summary_path):
                with open(summary_path) as f:
                    print(json.dumps(json.load(f), indent=2, ensure_ascii=False))


def cmd_clean(args):
    """Reset all persistence data."""
    paths = [
        "data/profile/ocean_profile.json",
        "data/neuro_symbolic_rules.json",
        "data/mind_relation.json",
        "data/mind_attention.json",
        "data/mind_mistakes.json",
    ]
    if args.all:
        paths.extend(["data/annotations/", "data/monitor/"])
        import shutil
    
    count = 0
    for p in paths:
        if os.path.isfile(p):
            os.remove(p); count += 1
        elif os.path.isdir(p) and args.all:
            shutil.rmtree(p, ignore_errors=True); count += 1
    
    print(f"Cleaned {count} items")
    if not args.all:
        print("Use --all to also clean annotations and monitor logs")


def main():
    parser = argparse.ArgumentParser(description="DialogMesh v6 CLI")
    sub = parser.add_subparsers(dest="command")
    
    # chat
    p_chat = sub.add_parser("chat", help="Interactive chat with profile tracking")
    p_chat.add_argument("--turns", type=int, default=10)
    
    # test
    p_test = sub.add_parser("test", help="Run benchmarks")
    p_test.add_argument("bench", nargs="?", default="all",
                        choices=["all", "live", "controlled", "implicit", "monitored"])
    
    # ab
    sub.add_parser("ab", help="A/B comparison test")
    
    # profile
    p_prof = sub.add_parser("profile", help="View/reset profile")
    p_prof.add_argument("--reset", action="store_true")
    
    # monitor
    p_mon = sub.add_parser("monitor", help="View session logs")
    p_mon.add_argument("--list", action="store_true")
    p_mon.add_argument("--last", nargs="?", const="jsonl", choices=["jsonl", "summary"])
    
    # clean
    p_clean = sub.add_parser("clean", help="Reset persistence")
    p_clean.add_argument("--all", action="store_true")
    
    args = parser.parse_args()
    
    commands = {
        "chat": cmd_chat, "test": cmd_test, "ab": cmd_ab,
        "profile": cmd_profile, "monitor": cmd_monitor, "clean": cmd_clean,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
