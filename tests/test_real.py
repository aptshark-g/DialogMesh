"""L1+L1.5 — real Stanza + DeepSeek pipeline."""
import sys, json, urllib.request, os, ssl
sys.path.insert(0, '.')

os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7877'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7877'

class DeepSeekLLM:
    def generate(self, prompt, max_tokens=200):
        proxy = urllib.request.ProxyHandler({'http':'http://127.0.0.1:7877','https':'http://127.0.0.1:7877'})
        opener = urllib.request.build_opener(proxy)
        req = urllib.request.Request("https://api.deepseek.com/v1/chat/completions",
            data=json.dumps({"model":"deepseek-chat","messages":[{"role":"user","content":prompt}],"max_tokens":max_tokens,"temperature":0.1}).encode(),
            headers={"Content-Type":"application/json","Authorization":"Bearer " + os.environ.get("DEEPSEEK_KEY", "") + ""})
        try:
            resp = opener.open(req, timeout=30)
            data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"]
            return content[content.index("{"):content.rindex("}")+1] if "{" in content else content
        except Exception as e:
            print(f"  DeepSeek error: {e}"); return ""

# Use exact stanza resources path
import stanza
import stanza.resources.common
stanza_dir = os.path.expandvars(r"%LOCALAPPDATA%\StanfordNLP\stanza\Cache\1.14.0\resources")
os.environ['STANZA_RESOURCES_DIR'] = stanza_dir
# Pre-load resources JSON
stanza.resources.common.load_resources_json(stanza_dir, os.path.join(stanza_dir, 'resources.json'))

nlp = stanza.Pipeline('zh', processors='tokenize,pos,lemma,depparse', use_gpu=False, logging_level='WARN', download_method=None)

from core.agent.association.l1_modifier import ModifierExtractor
from core.agent.association.l1_5_completer import CollaborativeCompleter

extractor = ModifierExtractor()
completer = CollaborativeCompleter(llm_provider=DeepSeekLLM())
tests = json.loads(open("tests/test_data_l1_5_completer.json", encoding='utf-8').read())["tests"]

for t in tests:
    print(f"\n=== {t['id']}: {t['text']} ===")
    doc = nlp(t["text"])
    modifiers, core = extractor.extract(doc)
    ctx = " ".join(f"[{m.role}]{m.text}→{m.head_word}" for h,ml in modifiers.items() for m in ml)
    print(f"  core: {core}")
    print(f"  modifiers: {ctx or '(none)'}")
    result = completer.complete(text=t["text"], modifier_context=ctx, entity_clusters=t.get("entity_clusters",{}))
    print(f"  completed: {result.completed_text[:80]}")
    print(f"  consensus={result.consensus} ambiguous={result.ambiguous}")
    print(f"  trace: {result.reasoning_trace[:150]}")
print("\n✅ Real pipeline done")
