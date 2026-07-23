"""BGE Mood Vector test — cosine(mood_profiles.yaml, input) → Z-axis."""
import sys, time
sys.path.insert(0, '.')
from sentence_transformers import SentenceTransformer
from core.agent.mood.mood_vector_library import MoodVectorLibrary

bge = SentenceTransformer('BAAI/bge-small-zh-v1.5')
lib = MoodVectorLibrary()
lib.load_bge('BAAI/bge-small-zh-v1.5')
print(f"Loaded: {len(lib.categories)} categories, {len(lib._descriptors)} descriptors\n")

tests = [
    ("这个地址是不是虚函数表指针？给出确切答案", 1.0),
    ("有没有什么思路来分析这个加密算法？", 0.0),
    ("做了三天逆向整个人都废了太难了", -1.0),
    ("scan 0x401000 and patch", 0.5),
    ("烂透了 这个packer根本解不开", -1.0),
    ("我太累了不想搞了", -1.0),
    ("我需要一个确切的答案", 1.0),
    ("可以解释一下底层机制吗", 0.0),
    ("help me fix this error", 1.0),
    ("what do you think", 0.0),
]

ok=0
for text, exp_z in tests:
    start = time.perf_counter()
    z = lib.classify(text)
    lat = (time.perf_counter()-start)*1000
    cat = "solution" if z>0.3 else ("mirror" if z<-0.3 else "explore")
    exp = "solution" if exp_z>0.3 else ("mirror" if exp_z<-0.3 else "explore")
    good=cat==exp
    if good: ok+=1
    print(f"{'✅' if good else '❌'} z={z:+.2f} {cat:10s} {lat:.0f}ms {text}")

print(f"\nBGE Mood: {ok}/{len(tests)}")
