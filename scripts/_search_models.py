# -*- coding: utf-8 -*-
"""搜索现成中文 SPO/关系抽取/OpenIE 模型（ModelScope + HF）。"""
import json
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
proxy = urllib.request.ProxyHandler({
    "http": "http://127.0.0.1:7877",
    "https": "http://127.0.0.1:7877"})
opener = urllib.request.build_opener(proxy)


def ms_search(q, limit=8):
    url = ("https://modelscope.cn/api/v1/dolphin/models"
           "?PageSize=%d&PageNumber=1&Search=%s"
           % (limit, urllib.parse.quote(q)))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=20) as r:
            data = json.loads(r.read())
        items = (data.get("Data") or {}).get("Model", []) or []
        if not items:
            print("  (empty)")
        for m in items[:limit]:
            print("  %s | %s" % (m.get("Path", "?"),
                                 str(m.get("Name", "?"))[:50]))
    except Exception as e:
        print("  ERR", str(e)[:90])


def hf_search(q, limit=6):
    url = ("https://huggingface.co/api/models?search=%s&limit=%d"
           "&sort=downloads&direction=-1"
           % (urllib.parse.quote(q), limit))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=20) as r:
            data = json.loads(r.read())
        if not data:
            print("  (empty)")
        for m in data:
            print("  %s (dl=%s)" % (m.get("modelId", "?"),
                                    m.get("downloads", 0)))
    except Exception as e:
        print("  ERR", str(e)[:80])


print("### ModelScope: 关系抽取")
ms_search("关系抽取")
time.sleep(0.5)
print("### ModelScope: 信息抽取")
ms_search("信息抽取")
time.sleep(0.5)
print("### ModelScope: OpenIE")
ms_search("openie")
time.sleep(0.5)
print("### ModelScope: 三元组")
ms_search("三元组抽取")
time.sleep(0.5)
print("### HF: GLiNER")
hf_search("gliner", 5)
time.sleep(0.5)
print("### HF: chinese relation extraction")
hf_search("chinese relation extraction", 5)
time.sleep(0.5)
print("### HF: gliner2 relation")
hf_search("gliner2", 5)
time.sleep(0.5)
print("### ModelScope 备选 API: uie")
url = "https://www.modelscope.cn/api/v1/models?PageSize=8&PageNumber=1&Search=" + urllib.parse.quote("UIE")
try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with opener.open(req, timeout=20) as r:
        data = json.loads(r.read())
    items = (data.get("Data") or {}).get("Model", []) or []
    if not items:
        print("  (empty)")
    for m in items[:8]:
        print("  %s | %s" % (m.get("Path", "?"), str(m.get("Name", "?"))[:50]))
except Exception as e:
    print("  ERR", str(e)[:90])
