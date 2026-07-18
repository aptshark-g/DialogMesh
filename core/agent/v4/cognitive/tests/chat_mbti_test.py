"""MBTI Chat Test — real conversation, implicit personality extraction.

You chat naturally. The system tracks STRENGTHEN/WEAKEN/REJECT from your style.
After N turns, it reports: personality_analytical (T-type) or personality_emotional (F-type).

No explicit labels, no MBTI test questions. Pure 暗提取.
"""
import sys, os, json
sys.path.insert(0, '.')
os.environ['DIALOGMESH_MONITOR'] = '1'

from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.v4.event_ir import DialogAdapter
from core.agent.v4.cognitive.tag_layer import TagAcquisitionEngine

KEY = "sk-20d76b2a00314beabb73dd8ab9d5743d"

def run_chat_test(turns: int = 10):
    """Start chat session — talk naturally, system extracts personality."""
    prov = OpenAIProvider("deepseek", {
        "api_key": KEY, "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
    })
    eng = CognitiveRuntimeEngine(llm_provider=prov)
    eng.start()
    ad = DialogAdapter()

    print("=" * 60)
    print("DialogMesh MBTI Chat Test — 暗提取人格分析")
    print("自然对话即可，系统会根据你的提问/讨论风格提取人格特征")
    print(f"对话 {turns} 轮后自动分析")
    print("=" * 60)

    for i in range(turns):
        print(f"\n[轮 {i+1}/{turns}] 请输入你想讨论的话题：")
        text = input("> ").strip()
        if text.lower() in ('quit', 'exit', 'q'):
            break
        if not text:
            continue

        response = eng.on_event(ad.adapt(text, "user", i + 1))
        # Print truncated response
        if response:
            short = response[:500] + ("..." if len(response) > 500 else "")
            print(f"\n系统回复: {short}")
        else:
            print("\n系统回复: [error — see log]")

    # Final analysis
    print("\n" + "=" * 60)
    print("人格分析结果")
    print("=" * 60)

    m = eng._trace_v3.meta_analyze()
    rd = m.get("reason_distribution", {})
    print(f"Transition 分布: {rd}")
    print(f"STRENGTHEN: {rd.get('strengthen', 0)}  WEAKEN: {rd.get('weaken', 0)}  REJECT: {rd.get('reject', 0)}")

    # Explicit infer
    tags = TagAcquisitionEngine().infer_from_trace(eng._trace_v3, eng._cognitive_profile)
    tb = eng._cognitive_profile.track_b

    print(f"\nTrackB 标签:")
    for k, v in tb.items():
        name = v.get('name', k) if isinstance(v, dict) else getattr(v, 'name', k)
        conf = v.get('confidence', 0) if isinstance(v, dict) else getattr(v, 'confidence', 0)
        src = v.get('source', '?') if isinstance(v, dict) else getattr(v, 'source', '?')
        print(f"  {name}: confidence={conf:.2f} source={src}")

    if "personality_analytical" in tb:
        print("\n→ 检测结果: T型思维（分析型）— 你的对话风格与系统架构高度对齐")
    elif "personality_emotional" in tb:
        print("\n→ 检测结果: F型思维（情感型）— 你的对话风格带来认知冲突或偏离")
    else:
        print("\n→ 信号不足，多聊几轮试试")

    return eng, tags


if __name__ == "__main__":
    run_chat_test(10)
