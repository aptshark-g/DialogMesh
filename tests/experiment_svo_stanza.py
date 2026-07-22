"""SVO + Semantic Distance experiment — with stanza dependency parse."""
import time, json, sys, math

# Load stanza once
import stanza
try:
    nlp_zh = stanza.Pipeline('zh', processors='tokenize,lemma,pos,depparse', verbose=False)
except:
    stanza.download('zh')
    nlp_zh = stanza.Pipeline('zh', processors='tokenize,lemma,pos,depparse', verbose=False)

try:
    nlp_en = stanza.Pipeline('en', processors='tokenize,pos,depparse', verbose=False)
except:
    stanza.download('en')
    nlp_en = stanza.Pipeline('en', processors='tokenize,pos,depparse', verbose=False)

print("Stanza: zh + en ready")


def extract_svo(text: str) -> tuple:
    """Dependency-parse SVO extraction."""
    if not text.strip():
        return "", "", ""
    
    # Detect language
    has_cjk = any(ord(c) > 0x2000 for c in text)
    nlp = nlp_zh if has_cjk else nlp_en
    doc = nlp(text)
    
    subj, verb, obj = "", "", ""
    for sent in doc.sentences:
        for word in sent.words:
            # Subject: nsubj dependency
            if word.deprel == 'nsubj' or word.deprel == 'nsubj:pass':
                subj = word.text
            # Root verb
            elif word.deprel == 'root' and word.upos == 'VERB':
                verb = word.text
            # Object: obj or dobj
            elif word.deprel in ('obj', 'dobj', 'iobj'):
                obj = word.text
    
    # Fallback: first/last tokens
    if not subj and doc.sentences:
        words = [w.text for w in doc.sentences[0].words]
        subj = words[0] if words else text[:5]
        obj = words[-1] if len(words) > 1 else words[0]
    if not verb and doc.sentences:
        words = [w.text for w in doc.sentences[0].words]
        verb = words[1] if len(words) > 1 else words[0]
    
    return subj, verb, obj


def ngram_cosine(s1: str, s2: str, n: int = 2) -> float:
    """N-gram overlap cosine — works for CJK with char bigrams."""
    if not s1 or not s2:
        return 0.0
    from collections import Counter
    def grams(t):
        if len(t) <= n:
            return Counter([t])
        return Counter(t[i:i+n] for i in range(len(t)-n+1))
    v1, v2 = grams(s1), grams(s2)
    all_keys = set(v1) | set(v2)
    if not all_keys:
        return 0.0
    dot = sum(v1.get(k,0) * v2.get(k,0) for k in all_keys)
    n1 = math.sqrt(sum(x**2 for x in v1.values()))
    n2 = math.sqrt(sum(x**2 for x in v2.values()))
    return dot / (n1 * n2) if n1*n2 > 0 else 0.0


def classify(cos: float) -> str:
    if cos > 0.4:   return "TOOL"
    elif cos > 0.2: return "ADVISOR"
    elif cos > 0.05: return "COMPANION"
    else:           return "UNKNOWN"


if __name__ == "__main__":
    tests = [
        ("扫描 0x401000 处的 4 bytes",      "TOOL"),
        ("分析这个加密算法的实现",              "ADVISOR"),
        ("能不能用机器学习预测内存地址的访问模式",  "COMPANION"),
        ("为什么这个函数被优化掉了",            "ADVISOR"),
        ("我是新手刚开始学逆向应该从哪里入手",    "COMPANION"),
        ("scan 4 bytes at 0x401000 and patch", "TOOL"),
        ("what packer is used for this binary", "ADVISOR"),
        ("先不说技术了，你做逆向的人是不是都比较有耐心", "COMPANION"),
        ("ok",                                "UNKNOWN"),
        ("",                                  "UNKNOWN"),
        ("先用frida hook然后angr约束求解再ghidra分析", "TOOL"),
        ("我有个想法：能不能用ML来预测哪些内存地址会被频繁访问", "COMPANION"),
        ("帮我看看这个地址0x7ff12345是不是有效的虚函数表指针", "ADVISOR"),
        ("修改这个函数把返回值改成0",            "TOOL"),
        ("这个加密算法先用AES再XOR密钥动态加载应该怎么分析", "ADVISOR"),
    ]

    print("SVO (stanza) + N-gram Cosine Experiment")
    print("=" * 80)
    results = []; correct = 0
    
    for text, expected in tests:
        start = time.perf_counter()
        subj, verb, obj = extract_svo(text)
        cos = ngram_cosine(subj, obj) if subj and obj else 0.0
        pred = classify(cos)
        latency = (time.perf_counter() - start) * 1000
        ok = pred == expected
        if ok: correct += 1
        print(f"{'✅' if ok else '❌'} {text[:40]:40s} S={subj:12s} O={obj:12s} cos={cos:.3f} → {pred:10s} ({expected})")
        results.append({"text":text[:50],"subj":subj,"obj":obj,"verb":verb,"cosine":round(cos,4),"predicted":pred,"expected":expected,"correct":ok,"latency_ms":round(latency,2)})

    print("=" * 80)
    print(f"Accuracy: {correct}/{len(tests)} ({correct/len(tests)*100:.0f}%)")
    avg_lat = sum(r["latency_ms"] for r in results)/len(results)
    print(f"Avg latency: {avg_lat:.1f}ms")

    with open('tests/test_performance/svo_stanza_data.jsonl','w',encoding='utf-8') as f:
        for r in results: f.write(json.dumps(r,ensure_ascii=False)+'\n')
    print(f"Saved to tests/test_performance/svo_stanza_data.jsonl")
