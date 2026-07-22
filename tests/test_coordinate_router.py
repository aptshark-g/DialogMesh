"""Coordinate Router test — V4.0 三维认知坐标验证."""

import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agent.v4.coordinate_router import (
    CognitiveCoordinate, SyntacticTerrain, MoodClassifier, CoordinateProjector
)


def test_mood_classifier():
    print("=== MoodClassifier (Z轴信号A) ===")
    tests = [
        ("这个地址是不是虚函数表指针？给出确切答案", True, False, 1.0),
        ("有没有什么思路来分析这个加密算法？", True, False, 0.0),
        ("做了三天逆向整个人都废了太难了", False, False, -1.0),
        ("scan 0x401000 and patch", False, True, 0.8),
        ("为什么这个函数被优化掉了？", True, False, 0.0),
        ("how do I reverse this binary", True, False, 0.0),
        ("烂透了 这个packer根本解不开", False, False, -1.0),
        ("你好", False, False, 0.0),
    ]
    for text, q, imp, exp in tests:
        z = MoodClassifier.classify(text, q, imp)
        ok = abs(z - exp) < 0.1
        print(f"{'✅' if ok else '❌'} z={z:+.1f} (exp={exp:+.1f}) {text[:50]}")
    print()


def test_coordinate_router():
    print("=== CognitiveCoordinate Router ===")
    
    # Load stanza
    import stanza
    try:
        nlp = stanza.Pipeline('zh', processors='tokenize,lemma,pos,depparse', verbose=False)
    except:
        stanza.download('zh')
        nlp = stanza.Pipeline('zh', processors='tokenize,lemma,pos,depparse', verbose=False)
    print("Stanza loaded")
    
    projector = CoordinateProjector(stanza_nlp=nlp)
    
    tests = [
        ("扫描 0x401000 处的 4 bytes", "近/简/解 → ATOMIC"),
        ("重构这段代码并补充单元测试和集成测试", "近/深/解 → PRECISION"),
        ("有没有什么思路来分析这个加密算法", "近/中/探 → EXPLORE or MIXED"),
        ("用量子退火算法优化物流路径，并论证可行性和成本效益", "远/深/探 → ABYSS"),
        ("做了三天逆向整个人都废了", "任意/简/镜 → PSYCHE"),
        ("scan 4 bytes at 0x401000 and patch the jump", "近/简/解 → ATOMIC"),
        ("虽然延迟飙升但若监控未报错且历史基线正常则需检查网络并重试", "近/深/解 → PRECISION"),
        ("你好 今天天气怎么样", "近/简/探 → ATOMIC or EXPLORE"),
        ("", "空 → MIXED default"),
        ("ok", "短 → MIXED default"),
    ]
    
    results = []
    print(f"{'输入':40s} {'X':>6s} {'Y':>6s} {'Z':>6s} {'Zone':12s} {'预期'}")
    print("-" * 90)
    
    for text, expected in tests:
        start = time.perf_counter()
        coord = projector.project(text)
        latency = (time.perf_counter() - start) * 1000
        
        zone = coord.zone()
        strategy = coord.strategy()
        
        print(f"{text[:38]:40s} {coord.x:6.3f} {coord.y:6.3f} {coord.z:+6.3f} "
              f"{zone:12s} {expected}")
        
        results.append({
            "text": text[:60],
            "x": coord.x, "y": coord.y, "z": coord.z,
            "zone": zone, "strategy": strategy["desc"],
            "expected": expected, "latency_ms": round(latency, 2),
        })
    
    print("-" * 90)
    zones = [r["zone"] for r in results]
    print(f"Zone distribution: {', '.join(f'{z}={zones.count(z)}' for z in set(zones))}")
    avg_lat = sum(r["latency_ms"] for r in results) / len(results)
    print(f"Avg latency: {avg_lat:.1f}ms (first call includes stanza warmup)")
    
    with open("tests/test_performance/coordinate_router_data.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("Saved to tests/test_performance/coordinate_router_data.jsonl")


if __name__ == "__main__":
    test_mood_classifier()
    test_coordinate_router()
