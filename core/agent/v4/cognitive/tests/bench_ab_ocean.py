"""AB Test: replay previous session with CoT+BFI fix, compare results.

Feeds same 10 questions into new engine. Shows before/after OCEAN + MBTI.
"""
import sys, os, json, time
sys.path.insert(0, '.')
os.environ['DIALOGMESH_MONITOR'] = '1'

from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.v4.event_ir import DialogAdapter

KEY = "sk-20d76b2a00314beabb73dd8ab9d5743d"

# Your 10 questions from previous session
QUESTIONS = [
    "有记忆吗？",
    "这么看来我们是新面孔，你觉得你当前的设计如何？你应该是只能看得见上下文以及一些agent给出的信息，依次来看你可以推测出什么？",
    "你对这个设计的看法如何？我希望看到详细的评估",
    "如果说人的交感神经是对应的，紧张和兴奋几乎类似，意味着把紧张引导到兴奋乃至愉悦才是最好的选择是吧？这无需消耗意志力而是顺应生理和神经训练，你怎么看？",
    "这个是典型的话题切换是吗？你觉得如果是你，你会怎么想？逻辑跳跃？你可以连贯起来吗？现在的对话树分类了吗？",
    "如果是镜子视角而非测试视角有没有可能？因为我是一个人测试，意味着这些可能是我ecn的记忆组块的存储主题，也可能是另一种少见可能，超长的逻辑链，你怎么看？",
    "实际上完全的可能的，换一个角度，写出这样系统的人大概率是自省度较高的，在对话里面应该也能看出来，这种类型的人往往容易紧张是吗？也许是高标准，自然容易想到如何解决，你觉得合理？",
    "有没有可能是假的？是我骗你的？在测试你的理解能力？也有没有可能是真的？真假的实际判断内核在于实际语言的隐形的关联线，引导你一下，你觉得这种提示词有没有可能让你能力更强？",
    "那你觉得你区分的核心是是吗？提示词的效果能否起作用？例如让你一步步推导，你能否给出一些信息？",
    "你觉得这个认知画像有起到辅助你的效果吗？还是阻碍了？",
]

# Previous results for comparison
PREV_OCEAN = {"O": 0.70, "C": 0.46, "E": 0.39, "A": 0.41, "N": 0.34,
              "NC": 0.75, "CS": 0.78, "DK": 0.65, "MS": 0.79, "CL": 0.72}
PREV_MBTI = "INTP"

print("=" * 70)
print("AB Test: CoT + BFI override vs Old OCEAN")
print(f"Old: {PREV_MBTI} {PREV_OCEAN}")
print("=" * 70)

prov = OpenAIProvider("deepseek", {
    "api_key": KEY, "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
})
eng = CognitiveRuntimeEngine(llm_provider=prov)
eng.start()
ad = DialogAdapter()

all_ocean = []
all_bfi = []
all_bfi_overrides = []

for i, text in enumerate(QUESTIONS):
    response = eng.on_event(ad.adapt(text, "user", i + 1))
    
    # Get current OCEAN state
    ocean = getattr(getattr(eng, '_ocean_analyst', None), 'profile', None)
    dims = dict(ocean.dims) if ocean else {}
    mbti = ocean.to_mbti() if ocean else "?"
    all_ocean.append(dict(dims))
    
    # Get BFI state
    cali = getattr(getattr(eng, '_bfi_calibrator', None), '_bfi_history', [])
    bfi = cali[-1]["bfi_scores"] if cali else {}
    all_bfi.append(dict(bfi))
    divergence = cali[-1].get("divergence", {}).get("total_divergence", 0) if cali else 0
    bfi_overrides = ocean_result.get("bfi_overrides", 0) if 'ocean_result' in dir() else 0
    
    print(f"T{i+1}: {mbti} C={dims.get('C',0):.2f} A={dims.get('A',0):.2f} "
          f"bfi_C={bfi.get('C',3)} div={divergence:.2f}")

final_dims = all_ocean[-1]
final_mbti = ocean.to_mbti() if ocean else "?"

print(f"\n{'=' * 70}")
print(f"  PREV:  {PREV_MBTI}  C={PREV_OCEAN['C']:.2f} A={PREV_OCEAN['A']:.2f}")
print(f"  AFTER: {final_mbti}  C={final_dims.get('C',0):.2f} A={final_dims.get('A',0):.2f}")
print(f"  Diff:  C: {final_dims.get('C',0)-PREV_OCEAN['C']:+.2f}  A: {final_dims.get('A',0)-PREV_OCEAN['A']:+.2f}")

# Final comparison
print(f"\n  {'✅ J detected' if final_dims.get('C',0)>0.55 else '❌ still P'}  "
      f"{'✅ F detected' if final_dims.get('A',0)>0.5 else '❌ still T'}")
print(f"{'=' * 70}")
