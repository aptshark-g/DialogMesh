# -*- coding: utf-8 -*-
"""下载 GLiNER multi-v2.1 到 models/gliner_multi-v2.1（走代理, 流式）。"""
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "https://huggingface.co/urchade/gliner_multi-v2.1/resolve/main/"
OUT = os.path.join("models", "gliner_multi-v2.1")
FILES = ["gliner_config.json", "model.safetensors", "README.md"]

proxy = urllib.request.ProxyHandler({
    "http": "http://127.0.0.1:7877",
    "https": "http://127.0.0.1:7877"})
opener = urllib.request.build_opener(proxy)
os.makedirs(OUT, exist_ok=True)

for fn in FILES:
    path = os.path.join(OUT, fn)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        print("skip (exists):", fn)
        continue
    url = BASE + fn
    print("downloading", fn, "...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with opener.open(req, timeout=120) as r, open(path + ".tmp", "wb") as f:
        total = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
            if total % (50 << 20) < (1 << 20):
                print("  %.1f MB" % (total / 1048576))
    os.replace(path + ".tmp", path)
    print("  done:", fn, "%.1f MB" % (os.path.getsize(path) / 1048576))
