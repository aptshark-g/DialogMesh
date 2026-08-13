# -*- coding: utf-8 -*-
"""中文编码验证: 文件脚本直接发网关（2026-08-11）。"""
import json
import urllib.request


def main():
    prompt = "把下面文本拆成 claims, 每行一条: 天空是蓝色的。太阳很亮。水是湿的。"
    print("prompt repr:", repr(prompt))
    body = json.dumps({
        "provider": "deepseek", "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048, "temperature": 0.0,
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8080/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer dm-client"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    print("content:", repr(d["choices"][0]["message"].get("content", "")[:200]))


if __name__ == "__main__":
    main()
