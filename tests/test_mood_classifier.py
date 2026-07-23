"""MoodClassifier test (standalone)."""
import sys; sys.path.insert(0, '.')
from core.agent.router.coordinate_router import MoodClassifier

tests = [
    ("这个地址是不是虚函数表指针？给出确切答案", True, False, 1.0),
    ("有没有什么思路来分析这个加密算法？", True, False, 0.0),
    ("做了三天逆向整个人都废了太难了", False, False, -1.0),
    ("scan 0x401000 and patch", False, True, 0.7),
    ("为什么这个函数被优化掉了？", True, False, 0.0),
    ("how do I reverse this binary", True, False, 0.0),
    ("烂透了 这个packer根本解不开", False, False, -1.0),
    ("你好", False, False, 0.0),
    ("分析这个加密算法", False, True, 0.7),
    ("what is the address", True, False, 1.0),
    ("help me understand this", False, True, 0.7),
    ("为什么", True, False, 0.0),
]

ok = 0
for t, q, i, e in tests:
    z = MoodClassifier.classify(t, q, i)
    good = abs(z - e) < 0.1
    if good: ok += 1
    print(f"{'✅' if good else '❌'} z={z:+.1f} (exp={e:+.1f}) {t[:50]}")
print(f"MoodClassifier: {ok}/{len(tests)}")
