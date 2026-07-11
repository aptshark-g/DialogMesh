"""v3.2 monitoring framework — lightweight event logging"""
import time, json


class Monitor:
    """Record and report module-level events across the v3.2 pipeline"""

    def __init__(self, verbose=False, log_file=None):
        self.events = []
        self.verbose = verbose
        self.log_file = log_file

    def record(self, module, event, data=None, duration=None, status="ok"):
        entry = {
            "module": module,
            "event": event,
            "timestamp": time.strftime("%H:%M:%S"),
            "duration_ms": round(duration, 1) if duration else 0,
            "status": status,
        }
        if data:
            entry["data"] = {k: str(v)[:60] for k, v in data.items()} if isinstance(data, dict) else str(data)[:200]
        self.events.append(entry)
        if self.verbose:
            msg = f"  [{module}.{event}] {status} ({entry['duration_ms']:.0f}ms)"
            print(msg, file=__import__("sys").stderr)

    def report(self):
        """Print full report to stderr"""
        print(file=__import__("sys").stderr)
        print("=" * 60, file=__import__("sys").stderr)
        print("  v3.2 Monitoring Report", file=__import__("sys").stderr)
        print("=" * 60, file=__import__("sys").stderr)
        print(f"  Events: {len(self.events)}", file=__import__("sys").stderr)
        print(file=__import__("sys").stderr)
        for e in self.events:
            print(f"  [{e['module']:>12}] {e['event']:<20} {e['status']:<6} {e['duration_ms']:>8.1f}ms", file=__import__("sys").stderr)
        print("=" * 60, file=__import__("sys").stderr)

    def to_json(self):
        return self.events

    def write_log(self, path):
        """Write structured log to file"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.events, ensure_ascii=False, indent=2))
