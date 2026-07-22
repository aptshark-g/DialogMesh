"""SVO + Distance classification experiment — no BGE, no keywords, pure structure.

Tests the hypothesis: 
  拆语法树 → 找主宾 → 距离近=近迁移 → 距离远=远迁移
Uses char n-gram overlap as semantic similarity proxy.
Replace with BGE embeddings when network available.
"""

import re, json, time, math
from collections import Counter


def extract_svo(text: str) -> tuple:
    """Simple SVO extraction — structural, language-agnostic."""
    text = text.strip()
    if not text:
        return "", "", ""
    
    # Split into tokens
    tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+|0x[0-9a-fA-F]+', text)
    if not tokens:
        return "", "", ""
    
    # Subject: first token or first noun-like token
    subj = tokens[0]
    
    # Object: last token or hex address
    obj_candidates = [t for t in tokens if t.startswith('0x')]
    if obj_candidates:
        obj = obj_candidates[-1]
    else:
        obj = tokens[-1] if len(tokens) > 1 else tokens[0]
    
    # Verb: second token or first verb-like (short action word)
    if len(tokens) >= 3:
        verb = tokens[1]
    elif len(tokens) == 2:
        verb = tokens[0]
    else:
        verb = tokens[0]
    
    return subj, verb, obj


def ngram_vector(text: str, n: int = 3) -> Counter:
    """Character n-gram frequency vector."""
    if not text:
        return Counter()
    grams = [text[i:i+n] for i in range(max(1, len(text)-n+1))]
    return Counter(grams)


def cosine_ngram(s1: str, s2: str, n: int = 3) -> float:
    """Cosine similarity via n-gram overlap (semantic proxy)."""
    v1 = ngram_vector(s1, n)
    v2 = ngram_vector(s2, n)
    all_keys = set(v1) | set(v2)
    if not all_keys:
        return 0.0
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in all_keys)
    norm1 = math.sqrt(sum(v**2 for v in v1.values()))
    norm2 = math.sqrt(sum(v**2 for v in v2.values()))
    if norm1 * norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def classify_by_distance(cosine: float) -> str:
    """Map cosine distance to expectation category."""
    if cosine > 0.5:
        return "TOOL"        # 近迁移: S/O 在同一领域
    elif cosine > 0.25:
        return "ADVISOR"     # 中近: 有一定关联
    elif cosine > 0.1:
        return "COMPANION"   # 中远: 探索/学习
    else:
        return "UNKNOWN"     # 远迁移: 跨域或无关联


if __name__ == "__main__":
    tests = [
        ("扫描 0x401000 处的 4 bytes", "TOOL"),
        ("分析这个加密算法的实现", "ADVISOR"),
        ("能不能用机器学习预测内存地址的访问模式", "COMPANION"),
        ("为什么这个函数被优化掉了", "ADVISOR"),
        ("我是新手刚开始学逆向应该从哪里入手", "COMPANION"),
        ("scan 4 bytes at 0x401000 and patch", "TOOL"),
        ("what packer is used for this binary", "ADVISOR"),
        ("先不说技术了，你做逆向的人是不是都比较有耐心", "COMPANION"),
        ("ok", "UNKNOWN"),
        ("", "UNKNOWN"),
        ("先用frida hook然后angr约束求解再ghidra分析比对结果", "TOOL"),
        ("我有个想法：能不能用ML来预测哪些内存地址会被频繁访问", "COMPANION"),
        ("帮我看看这个地址0x7ff12345是不是有效的虚函数表指针", "ADVISOR"),
        ("修改这个函数把返回值改成0", "TOOL"),
        ("这个加密算法先用AES再XOR密钥动态加载应该怎么分析", "ADVISOR"),
    ]

    print("SVO + N-gram Cosine Distance Experiment")
    print("=" * 80)
    results = []
    correct = 0
    
    for text, expected in tests:
        start = time.perf_counter()
        subj, verb, obj = extract_svo(text)
        
        if subj and obj:
            cosine = cosine_ngram(subj, obj)
        else:
            cosine = 0.0
        
        predicted = classify_by_distance(cosine)
        latency = (time.perf_counter() - start) * 1000
        
        is_correct = predicted == expected
        if is_correct:
            correct += 1
        
        marker = "✅" if is_correct else "❌"
        results.append({
            "text": text[:50],
            "subj": subj,
            "obj": obj,
            "verb": verb,
            "cosine": round(cosine, 4),
            "predicted": predicted,
            "expected": expected,
            "correct": is_correct,
            "latency_ms": round(latency, 2),
        })
        
        print(f"{marker} {text[:45]:45s} S={subj:10s} O={obj:10s} cos={cosine:.3f} → {predicted:10s} ({expected})")
    
    print("=" * 80)
    print(f"Accuracy: {correct}/{len(tests)} ({correct/len(tests)*100:.0f}%)")
    avg_lat = sum(r["latency_ms"] for r in results) / len(results)
    print(f"Avg latency: {avg_lat:.2f}ms")

    # Confusion summary
    from collections import defaultdict
    confusion = defaultdict(lambda: defaultdict(int))
    for r in results:
        confusion[r["expected"]][r["predicted"]] += 1
    
    print("\nConfusion Matrix:")
    print(f"{'':12s}", end="")
    for p in ["TOOL", "ADVISOR", "COMPANION", "UNKNOWN"]:
        print(f"{p:>10s}", end="")
    print()
    for e in ["TOOL", "ADVISOR", "COMPANION", "UNKNOWN"]:
        print(f"{e:12s}", end="")
        for p in ["TOOL", "ADVISOR", "COMPANION", "UNKNOWN"]:
            print(f"{confusion[e][p]:>10d}", end="")
        print()

    # Distribution
    print(f"\nCosine distribution: min={min(r['cosine'] for r in results):.3f} "
          f"max={max(r['cosine'] for r in results):.3f} "
          f"avg={sum(r['cosine'] for r in results)/len(results):.3f}")

    with open('tests/test_performance/svo_distance_data.jsonl', 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f"Saved to tests/test_performance/svo_distance_data.jsonl")
