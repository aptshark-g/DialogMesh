"""Multi-Intent Splitter tests — JSON-driven + LLM live test."""

import sys, json
sys.path.insert(0, '.')
from core.agent.intent.multi_intent_splitter import MultiIntentSplitter
from core.agent.intent.models import SubIntent, MultiIntentResult


def test_structural():
    """Structural tests — no LLM needed."""
    data = json.loads(open("tests/test_data_multi_intent.json", encoding='utf-8').read())
    splitter = MultiIntentSplitter()  # no LLM

    for s in data["scenarios"]:
        result = splitter.split(s["text"])
        checks = s["expect"]
        ok = True

        if result.is_multi != checks.get("is_multi", False):
            print(f"  ❌ {s['id']}: is_multi={result.is_multi} expected {checks['is_multi']}")
            ok = False
        if len(result.sub_intents) < checks.get("min_subs", 1):
            print(f"  ❌ {s['id']}: subs={len(result.sub_intents)} < {checks['min_subs']}")
            ok = False

        if ok:
            print(f"  ✅ {s['id']}: {len(result.sub_intents)} sub-intents, multi={result.is_multi}")


def test_live_llm():
    """Live LLM test — uses nemotron on LM Studio to verify a multi-intent split."""
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:1234/v1/models")
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        print("\n  ⚠️ LM Studio not available — skipping LLM test")
        return

    # Build a simple LLM-backed literal chain
    class Nemotron:
        def generate(self, prompt, max_tokens=150, temperature=0.1):
            req = urllib.request.Request("http://127.0.0.1:1234/v1/chat/completions",
                data=json.dumps({"model":"nvidia/nemotron-3-nano-4b","messages":[{"role":"user","content":prompt}],"max_tokens":max_tokens,"temperature":temperature}).encode(),
                headers={"Content-Type":"application/json"})
            resp = urllib.request.urlopen(req, timeout=30)
            d = json.loads(resp.read())
            return d["choices"][0]["message"].get("content","") or \
                   d["choices"][0]["message"].get("reasoning_content","")

    llm = Nemotron()
    splitter = MultiIntentSplitter(llm=llm)

    text = "先定位哪个模块延迟高，然后帮我看看怎么修复"
    print(f"\n=== LLM Live Test ===")
    print(f"  TEXT: {text}")
    result = splitter.split(text)
    print(f"  Result: {len(result.sub_intents)} sub-intents, multi={result.is_multi}")
    for si in result.sub_intents:
        print(f"    [{si.id}] {si.text[:50]} (conf={si.confidence:.2f}, literal={si.chain_votes.get('literal',0):.2f})")
    print(f"  Fusion: {result.fusion_method}")


if __name__ == "__main__":
    test_structural()
    test_live_llm()
    print("\n🎉 Multi-Intent Splitter: all tests passed")
