# -*- coding: utf-8 -*-
"""GLiNER2 multi 中文 SPO 抽取实测: 定义 subject/predicate/object 标签。"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gliner import GLiNER

model = GLiNER.from_pretrained("models/gliner_multi-v2.1")
print("model loaded")

def try_labels(model, sentence, labels):
    ents = model.predict_entities(sentence, labels)
    print("  labels=%s -> %s" % (labels[:3], [(e["label"], e["text"]) for e in ents]))

SENTENCES = [
    "情绪的根源是预期失衡和惯性破坏",
    "记忆点锚定认知判断",
    "主动降维的核心在于可控性",
    "DMN与ECN的激活比值决定认知加工模式",
    "梯度下降是深度学习常用的优化方法",
]

for s in SENTENCES:
    print("\nS:", s)
    try_labels(model, s, ["subject", "predicate", "object"])
    try_labels(model, s, ["主语", "谓语", "宾语"])
    try_labels(model, s, ["人物", "概念", "关系"])
    try_labels(model, s, ["organization", "concept"])

print("\n" + "=" * 40)
print("ENGLISH 对照（同样 SPO 标签）")
EN_SENTENCES = [
    "The root of emotion is expectation imbalance",
    "Memory points anchor cognitive judgment",
    "Gradient descent is a common optimization method",
    "DMN and ECN determine the cognitive processing mode",
    "The user login system contains JWT authentication",
]
for s in EN_SENTENCES:
    print("\nS:", s)
    try_labels(model, s, ["subject", "predicate", "object"])
    try_labels(model, s, ["person", "concept", "method"])
