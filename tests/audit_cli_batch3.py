"""Batch 3: CLI deep audit — run commands, check for stub/empty/error behavior."""
import sys, json, subprocess, os
# Key commands to test (representative of each module)
tests = [
    ("engine status", "engine,status"),
    ("engine state", "engine,state"),
    ("engine stop", "engine,stop"),
    ("session list", "session,list"),
    ("session create", "session,create"),
    ("discourse tree", "dt,show"),
    ("discourse blocks", "d,show"),
    ("pcr show", "pcr,show"),
    ("intent show", "intent,show"),
    ("behavior show", "behavior,show"),
    ("behavior stats", "behavior,stats"),
    ("meta show", "meta,show"),
    ("meta stats", "meta,stats"),
    ("assoc show", "assoc,show"),
    ("assoc stats", "assoc,stats"),
    ("obs show", "obs,show"),
    ("profile show", "profile,show"),
    ("profile ocean", "profile,ocean"),
    ("concepts show", "concepts,show"),
    ("mind show", "mind,show"),
    ("rules show", "rules,show"),
    ("engineering show", "engineering,show"),
    ("annotations list", "annotations,list"),
    ("knowledge stats", "knowledge,stats"),
    ("task list", "task,list"),
    ("graph show", "graph,show"),
    ("chunk stats", "chunk,stats"),
    ("meta show2", "meta,show"),
    ("engine start", "engine,start"),
]

# Since cli_main may not exist with that signature, test via subprocess instead
print("═══ CLI 深度核查 ═══")
print("(使用 dm 命令入口测试)\n")

import subprocess as sp
results = []
for label, cmd in tests:
    cmd_main, cmd_op = cmd.split(",")
    args = [cmd_main, cmd_op]
    try:
        proc = sp.run(
            [sys.executable, "core/agent/cli/entry.py", *args],
            capture_output=True, text=True, timeout=10,
            cwd=r"C:\Users\APTShark\PycharmProjects\DialogMesh"
        )
        out = (proc.stdout or "")[:120].strip()
        err = (proc.stderr or "")[:80].strip()
        has_output = len(out) > 5
        status = "✅" if proc.returncode == 0 and has_output else ("⚠️" if proc.returncode == 0 else "❌")
        results.append((label, status, proc.returncode, out))
        print(f"  {status} {label:<22} rc={proc.returncode} → {out[:60]}")
    except sp.TimeoutExpired:
        results.append((label, "⏱", -1, "timeout"))
        print(f"  ⏱ {label:<22} timeout")
    except Exception as ex:
        results.append((label, "❌", -1, str(ex)[:60]))
        print(f"  ❌ {label:<22} {str(ex)[:60]}")

print(f"\n═══ 汇总 ═══")
ok = sum(1 for _, s, _, _ in results if s == "✅")
warn = sum(1 for _, s, _, _ in results if s == "⚠️")
err = sum(1 for _, s, _, _ in results if s == "❌")
timeout = sum(1 for _, s, _, _ in results if s == "⏱")
print(f"  ✅ {ok}  ⚠️ {warn}  ❌ {err}  ⏱ {timeout}  (总 {len(results)})")
