# -*- coding: utf-8 -*-
"""未解析双链目标构成分析（2026-08-11）。"""
import glob
import os
import re
import sys

sys.path.insert(0, ".")

VAULT = r"C:\Users\APTShark\Documents\Obsidian Vault\dialogmesh-design"


def main():
    vault_names = {
        os.path.splitext(os.path.basename(f))[0]
        for f in glob.glob(os.path.join(VAULT, "*.md"))}
    # docs 全部 md 文件名（不含扩展）
    docs_names = set()
    for f in glob.glob("docs/**/*.md", recursive=True):
        docs_names.add(os.path.splitext(os.path.basename(f))[0])
    unresolved = set()
    total_links = 0
    for fp in glob.glob(os.path.join(VAULT, "*.md")):
        text = open(fp, encoding="utf-8").read()
        for t in re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text):
            total_links += 1
            target = t.split("#")[0].strip()
            if target not in vault_names:
                unresolved.add(target)
    mapped_to_docs = unresolved.intersection(docs_names)
    print("总双链: %d | 解析到 vault: %d | 未解析: %d" % (
        total_links, total_links - len(unresolved), len(unresolved)))
    print("未解析但映射到 docs 文件: %d" % len(mapped_to_docs))
    print("真未解析（vault+docs 都没有）: %d" % (len(unresolved) - len(mapped_to_docs)))
    print("映射示例:", sorted(mapped_to_docs)[:15])


if __name__ == "__main__":
    main()
