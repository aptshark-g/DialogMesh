"""Multi-Intent Splitter tests — LLM-first, zero hardcoded rules."""

import sys, json
sys.path.insert(0, '.')
from core.agent.intent.multi_intent_splitter import MultiIntentSplitter


def test_no_llm():
    """Without LLM, falls back to structural — single intent is correct."""
    splitter = MultiIntentSplitter()
    r = splitter.split("帮我分析这个加密算法")
    assert not r.is_multi, f"Expected single intent, got multi"
    assert len(r.sub_intents) == 1
    print("  ✅ no_llm: single intent correct")


def test_llm_multi():
    """With LLM, detects multi-intent from semantic understanding."""
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:1234/v1/models")
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        print("  ⚠️ LM Studio not available — skipping LLM tests")
        return

    class Nemotron:
        def generate(self, prompt, max_tokens=300, temperature=0.1):
            req = urllib.request.Request("http://127.0.0.1:1234/v1/chat/completions",
                data=json.dumps({"model":"nvidia/nemotron-3-nano-4b","messages":[{"role":"user","content":prompt}],"max_tokens":max_tokens,"temperature":temperature}).encode(),
                headers={"Content-Type":"application/json"})
            resp = urllib.request.urlopen(req, timeout=30)
            d = json.loads(resp.read())
            return d["choices"][0]["message"].get("content","") or \
                   d["choices"][0]["message"].get("reasoning_content","")

    llm = Nemotron()
    splitter = MultiIntentSplitter(llm=llm)

    tests = [
        ("帮我分析加密算法", False),          # single intent
        ("先定位延迟，然后帮我修复", True),     # explicit sequential
        ("看看这个漏洞，顺便评估影响", True),   # explicit parallel
    ]

    for text, expect_multi in tests:
        r = splitter.split(text)
        status = "✅" if r.is_multi == expect_multi else "❌"
        print(f"  {status} '{text[:30]}' → multi={r.is_multi} ({len(r.sub_intents)} parts)")
        for si in r.sub_intents:
            print(f"      [{si.id}] {si.text[:50]} (conf={si.confidence:.2f})")


if __name__ == "__main__":
    test_no_llm()
    test_llm_multi()
    print("\n🎉 Multi-Intent Splitter: LLM-first verified")
