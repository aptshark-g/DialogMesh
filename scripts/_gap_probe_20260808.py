# -*- coding: utf-8 -*-
"""排查: 注册/定义但未接线的组件（2026-08-08）— 输出 UTF-8 文件"""
import sys
import re
from pathlib import Path

SECTION = sys.argv[1] if len(sys.argv) > 1 else "all"  # registry | stub | classes | all

ROOT = Path("core/agent")
PY = [
    p for p in ROOT.rglob("*.py")
    if "tests" not in str(p) and "un_use" not in str(p) and "archived" not in str(p)
]
FILES = {str(p): p.read_text(encoding="utf-8", errors="ignore") for p in PY}
OUT = []


def log(*a):
    OUT.append(" ".join(str(x) for x in a))


def grep(pattern, files=None):
    rx = re.compile(pattern)
    out = []
    for fp, txt in FILES.items():
        for i, line in enumerate(txt.splitlines(), 1):
            if rx.search(line):
                out.append((Path(fp), i, line.strip()[:110]))
    return out


def count_refs(name):
    """全文计数某名字的生产引用（不做逐行, 快）."""
    rx = re.compile(rf"\b{re.escape(name)}\b")
    total = 0
    for fp, txt in FILES.items():
        total += len(rx.findall(txt))
    return total


# 1) registry 组件零消费
reg_names = []
if SECTION in ("all", "registry"):
    for _p, _i, line in grep(r"_registry\.register\(|r\.register\("):
        m = re.search(r'register\(\s*"([a-z_0-9]+)"', line)
        if m and m.group(1) not in reg_names:
            reg_names.append(m.group(1))
    log("=" * 70)
    log(f"[1] registry 组件 {len(reg_names)} 个 - 零消费列表")
    zero = []
    for name in reg_names:
        attr = f"_{name}"
        consumers = [
            c for c in grep(rf"\b{attr}\b")
            if "registry" not in str(c[0]) and "bootstrap" not in str(c[0])
        ]
        if not consumers:
            zero.append(name)
            log(f"  ZERO-CONSUME: {name}")
    log(f"  零消费 {len(zero)} 个: {zero}")

# 2) 占位/未实现标记
if SECTION in ("all", "stub"):
    log("=" * 70)
    log("[2] 占位/未实现标记")
    for pat in [
        r"deferred",
        r"NotImplementedError",
        r"\bstub\b",
        r"placeholder",
        r"TODO.*implement",
        r"not implemented",
    ]:
        hits = grep(pat)
        log(f"  --- {pat}: {len(hits)} 处 ---")
        for p, i, line in hits[:15]:
            log(f"    {str(p).replace(chr(92), '/')}:{i} {line}")

# 3) 零引用类
if SECTION in ("all", "classes"):
    log("=" * 70)
    log("[3] 零引用类（生产代码无引用）")
    classes = []
    for p in PY:
        txt = FILES[str(p)]
        for m in re.finditer(r"^class (\w+)", txt, re.M):
            classes.append((m.group(1), p))
    log(f"  共 {len(classes)} 个类定义")
    for cls, p in classes:
        # 定义文件自身 1 次; 引用数 <=1 视为零消费（含自引用）
        if count_refs(cls) <= 1:
            log(f"  ZERO-REF: {cls}  ({str(p).replace(chr(92), '/')})")

Path("data/_gap_scan_20260808.txt").write_text("\n".join(OUT), encoding="utf-8")
print("done, lines:", len(OUT))
