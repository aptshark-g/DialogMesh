# -*- coding: utf-8 -*-
"""下载 mdeberta-v3-base tokenizer/config 到 models/mdeberta-v3-base。"""
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "https://huggingface.co/microsoft/mdeberta-v3-base/resolve/main/"
OUT = os.path.join("models", "mdeberta-v3-base")
FILES = ["tokenizer_config.json"]

proxy = urllib.request.ProxyHandler({
    "http": "http://127.0.0.1:7877",
    "https": "http://127.0.0.1:7877"})
opener = urllib.request.build_opener(proxy)
os.makedirs(OUT, exist_ok=True)

for fn in FILES:
    path = os.path.join(OUT, fn)
    if os.path.exists(path) and os.path.getsize(path) > 100:
        print("skip:", fn)
        continue
    for attempt in range(4):
        print("downloading", fn, "(attempt %d)" % (attempt + 1))
        try:
            req = urllib.request.Request(BASE + fn, headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=180) as r, open(path + ".tmp", "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(path + ".tmp", path)
            print("  done:", fn, os.path.getsize(path))
            break
        except Exception as e:
            print("  retry:", str(e)[:80])
            import time
            time.sleep(2)
