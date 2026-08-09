"""DialogMesh v4 — Cognitive Runtime entry point.

Usage:
    python main.py                         # Interactive mode
    python main.py --event "add monitoring" # Send single event
    python main.py --daemon                # Background mode

v4 cognitive pipeline: Event -> Observation -> Hypothesis -> Knowledge -> Skill
"""
from __future__ import annotations
import argparse, sys, time, signal


def main():
    parser = argparse.ArgumentParser(description="DialogMesh v4 Cognitive Runtime")
    parser.add_argument("--event", "-e", help="Send a single user event")
    parser.add_argument("--config", "-c", help="Path to runtime.yaml")
    parser.add_argument("--daemon", "-d", action="store_true", help="Run in background")
    parser.add_argument("--status-interval", type=int, default=0,
                        help="Print status every N seconds (daemon mode)")
    args = parser.parse_args()

    from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
    from core.agent.v4.event_ir import EventIR

    engine = CognitiveRuntimeEngine(config_path=args.config)
    engine.start()
    print("v4 Cognitive Runtime started")

    def shutdown(signum=None, frame=None):
        print("\nShutting down...")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    if args.event:
        event = EventIR(
            id=f"cli_{int(time.time() * 1000)}",
            kind="dialog.message",
            payload={"text": args.event, "source": "main.py"},
        )
        engine.on_event(event)
        print(f"Event processed: {args.event[:60]}")

        engine.trigger_checkpoint()
        print("Checkpoint complete")
        engine.stop()
        return

    if args.daemon:
        print("Daemon mode. Press Ctrl+C to stop.")
        last_status = 0
        while True:
            time.sleep(1)
            if args.status_interval > 0:
                last_status += 1
                if last_status >= args.status_interval:
                    last_status = 0
                    for name, stats in engine.stats.items():
                        print(f"  {name}: {stats.trigger_count} triggers, "
                              f"{stats.success_count} ok, {stats.failure_count} fail")
    else:
        print("Interactive mode. Type text to send events. Ctrl+C to stop.")
        try:
            while True:
                text = input("> ").strip()
                if not text:
                    continue
                if text.lower() in ("quit", "exit", "q"):
                    break
                if text == "status":
                    for name, stats in engine.stats.items():
                        print(f"  {name}: {stats.trigger_count} triggers, "
                              f"{stats.success_count} ok, {stats.failure_count} fail")
                    continue
                if text == "checkpoint":
                    engine.trigger_checkpoint()
                    print("Checkpoint triggered")
                    continue

                event = EventIR(
                    id=f"cli_{int(time.time() * 1000)}",
                    kind="dialog.message",
                    payload={"text": text, "source": "main.py"},
                )
                engine.on_event(event)
        except (KeyboardInterrupt, EOFError):
            pass

    engine.stop()
    print("v4 Cognitive Runtime stopped")


if __name__ == "__main__":
    main()
