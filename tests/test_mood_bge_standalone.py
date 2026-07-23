"""BGE Mood Vector — standalone, no core imports"""
import time, math, yaml
from pathlib import Path
from sentence_transformers import SentenceTransformer
import numpy as np

# Load mood_profiles.yaml directly
config = yaml.safe_load(open('config/mood_profiles.yaml', encoding='utf-8'))
profiles = config['profiles']

# Build descriptor vectors
descriptors = []
categories = []
z_values = {}
for cat, prof in profiles.items():
    for desc in prof['descriptors']:
        descriptors.append(desc)
        categories.append(cat)
    z_values[cat] = prof.get('z_value', 0.0)

print(f"Loading BGE...")
bge = SentenceTransformer('BAAI/bge-small-zh-v1.5')
print(f"Encoding {len(descriptors)} descriptors...")
desc_vecs = np.array([bge.encode(d, normalize_embeddings=True) for d in descriptors])
print(f"Ready: {len(desc_vecs)} vectors, {desc_vecs.shape[1]} dims\n")

def classify(text):
    if not text.strip(): return 0.0
    v = bge.encode(text, normalize_embeddings=True)
    sims = np.dot(desc_vecs, v)
    best = int(np.argmax(sims))
    return z_values[categories[best]]

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
    ("先不说技术了你觉得做逆向的人是不是都比较有耐心", -0.3),
    ("帮我分析这个加密算法", 0.3),
]

ok = 0; total_lat = 0
for text, exp_z in tests:
    start = time.perf_counter()
    z = classify(text)
    lat = (time.perf_counter()-start)*1000
    total_lat += lat
    cat = "solution" if z>0.3 else ("mirror" if z<-0.3 else "explore")
    exp = "solution" if exp_z>0.3 else ("mirror" if exp_z<-0.3 else "explore")
    good = cat==exp
    if good: ok+=1
    print(f"{'✅' if good else '❌'} z={z:+.2f} {cat:10s} {lat:.0f}ms | {text[:55]}")

print(f"\nBGE Mood: {ok}/{len(tests)} ({ok/len(tests)*100:.0f}%)")
print(f"Avg latency: {total_lat/len(tests):.0f}ms")
print(f"Config: config/mood_profiles.yaml ({len(descriptors)} descriptors, editable)")
