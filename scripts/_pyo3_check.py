# -*- coding: utf-8 -*-
"""查 pyo3 0.21 支持的 Python 版本（2026-08-11）。"""
import re
import urllib.request


def main():
    proxies = {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
    url = "https://raw.githubusercontent.com/PyO3/pyo3/v0.21.2/CHANGELOG.md"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    text = opener.open(req, timeout=20).read().decode("utf-8", errors="replace")
    out = []
    # 找 0.21 版本节的 Python 支持声明
    for m in re.finditer(r"Python 3\.\d+", text[:2000]):
        out.append(m.group(0))
    # 找 3.13 支持引入的版本
    for m in re.finditer(r"[^\n]*3\.13[^\n]*", text):
        out.append(m.group(0)[:120])
    with open("_pyo3_out.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(out[:15]) or "未找到")
    print("done")


if __name__ == "__main__":
    main()
