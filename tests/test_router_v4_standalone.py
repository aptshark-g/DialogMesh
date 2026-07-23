"""RouterV4 standalone test — minimal imports, maximum speed."""
import time, re, math, yaml, numpy as np
import stanza
from sentence_transformers import SentenceTransformer

nlp = stanza.Pipeline('zh', processors='tokenize,lemma,pos,depparse', verbose=False)
bge = SentenceTransformer('BAAI/bge-small-zh-v1.5')
config = yaml.safe_load(open('config/mood_profiles.yaml', encoding='utf-8'))
descs, cats, zv = [], [], {}
for cat, prof in config['profiles'].items():
    for d in prof['descriptors']: descs.append(d); cats.append(cat)
    zv[cat] = prof.get('z_value', 0.0)
mood_vecs = np.array([bge.encode(d, normalize_embeddings=True) for d in descs])

print(f"Ready: stanza + BGE mood ({len(descs)} descs)\n")

def route(text):
    result = {}
    # Y: Stanza STC
    doc = nlp(text)
    md, cc = 0, 0
    for sent in doc.sentences:
        for w in sent.words:
            if w.deprel in ('conj','cc','parataxis'): cc += 1
            d = 1; cur = w
            while cur.head > 0 and d < 50: d += 1; cur = sent.words[cur.head-1]
            md = max(md, d)
    raw = min(md/5, 1.5)*0.4 + min(cc/3, 1.5)*0.4
    y = round(1.0/(1.0+math.exp(-(raw-0.3)*4.0)), 3)
    
    # Z: BGE Mood
    v = bge.encode(text, normalize_embeddings=True) if text.strip() else np.zeros(512)
    z = zv[cats[int(np.argmax(np.dot(mood_vecs, v)))]]
    
    # X: simple heuristic
    tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+|0x[0-9a-fA-F]+', text)
    x = 0.4 if len(tokens) >= 2 else 0.3
    
    # Zone
    if z < -0.5: zone = "PSYCHE"
    elif x < 0.3 and y < 0.3: zone = "ATOMIC"
    elif x > 0.6 and y > 0.6 and z > 0.3: zone = "ABYSS"
    elif x < 0.5 and y > 0.4 and z > 0: zone = "PRECISION"
    elif x > 0.4 and y < 0.4 and z <= 0: zone = "EXPLORE"
    else: zone = "MIXED"
    
    return x, y, z, zone

tests = [
    ("scan 0x401000 and patch", "ATOMIC/PRECISION"),
    ("做了三天逆向整个人都废了太难了不想搞了", "PSYCHE"),
    ("有没有什么思路来分析这个加密算法", "EXPLORE"),
    ("用量子退火优化物流路径并论证可行性", "ABYSS"),
    ("先不说技术了你觉得做逆向的人是不是都比较有耐心", "PSYCHE"),
    ("修改这个函数把返回值改成0", "ATOMIC/PRECISION"),
    ("为什么这个函数被优化掉了", "EXPLORE"),
]

for text, exp in tests:
    start = time.perf_counter()
    x, y, z, zone = route(text)
    lat = (time.perf_counter()-start)*1000
    costs = {"ATOMIC":0,"PSYCHE":100,"EXPLORE":200,"PRECISION":400,"ABYSS":1000,"MIXED":300}
    print(f"({x:.2f},{y:.2f},{z:+.2f}) → {zone:12s} {costs[zone]:4d}ms {lat:.0f}ms | {text[:50]}")

print(f"\nV4.0 Router: 3D coordinate → zone → strategy")
