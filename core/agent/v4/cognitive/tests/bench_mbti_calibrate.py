"""MBTI Calibration — standard personality test for external validation.

16 MBTI types × 4 questions per type = 64 prompts.
Measures: WEAKEN/STRENGTHEN/REJECT per type.
Calibrates: what WEAKEN level corresponds to each personality facet.

Dimensions: E/I (extraversion), S/N (intuition), T/F (thinking/feeling), J/P (judging/perceiving)
Prediction: T-types (INTJ,ISTJ) → low WEAKEN (<3), F-types (ENFP,ESFP) → high WEAKEN (>5)
"""
import sys, os, json, math
sys.path.insert(0, '.')
os.environ['DIALOGMESH_MONITOR'] = '1'
import numpy as np
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.v4.event_ir import DialogAdapter

KEY = "sk-20d76b2a00314beabb73dd8ab9d5743d"

# MBTI test prompts — each type speaks in its characteristic style
MBTI_PROMPTS = {
    "INTJ": [
        "I approach problems through systematic analysis and logical frameworks.",
        "I prefer working independently on complex, long-term strategic challenges.",
        "Emotions are secondary to objective data — show me the evidence.",
        "I plan everything meticulously before taking action.",
    ],
    "ENTJ": [
        "I take charge and organize teams toward clear strategic goals.",
        "I make decisions quickly based on logical analysis and long-term vision.",
        "I expect efficiency and competence. Results matter more than feelings.",
        "I enjoy leading complex projects and delegating to achieve outcomes.",
    ],
    "INTP": [
        "I love exploring abstract theoretical frameworks and logical models.",
        "I question assumptions constantly — every system has hidden flaws.",
        "I need time alone to process complex ideas deeply.",
        "I value precision and intellectual rigor above social harmony.",
    ],
    "ENTP": [
        "I thrive on debating ideas and exploring unconventional possibilities.",
        "I see connections others miss — innovation comes from challenging norms.",
        "I get bored with routine and need constant intellectual stimulation.",
        "I argue for the sake of testing ideas, not winning.",
    ],
    "INFJ": [
        "I sense the emotional undercurrents in every situation intuitively.",
        "I need my work to have deeper meaning and purpose beyond profit.",
        "I understand people's unspoken motivations better than they do.",
        "I seek harmony and authenticity in all my relationships.",
    ],
    "ENFJ": [
        "I naturally inspire and motivate people to become their best selves.",
        "I feel responsible for the emotional well-being of my team.",
        "I read social dynamics effortlessly and adapt accordingly.",
        "I believe in developing people, not just achieving tasks.",
    ],
    "INFP": [
        "I live by my deeply held personal values above external expectations.",
        "I feel things intensely and express myself through creative work.",
        "I seek authenticity and meaning in everything I do.",
        "I need freedom to explore ideas without rigid structure.",
    ],
    "ENFP": [
        "I'm energized by connecting with people and exploring new possibilities!",
        "My intuition guides me more than rigid logic or detailed plans.",
        "I see potential in everyone and get excited about what could be!",
        "I thrive on variety, spontaneity, and emotional connections.",
    ],
    "ISTJ": [
        "I follow established procedures and value reliability above all.",
        "I keep detailed records and check facts before making decisions.",
        "I respect tradition and proven methods — they exist for a reason.",
        "I fulfill my commitments precisely and expect others to do the same.",
    ],
    "ESTJ": [
        "I run efficient operations with clear rules and accountability.",
        "I make decisions based on concrete facts, not theoretical possibilities.",
        "I expect people to follow through on commitments without excuses.",
        "I value order, structure, and predictable outcomes.",
    ],
    "ISFJ": [
        "I quietly support others through practical help and dedicated service.",
        "I remember personal details about people and care deeply about their needs.",
        "I work diligently behind the scenes to ensure everything runs smoothly.",
        "I value stability, loyalty, and harmonious relationships.",
    ],
    "ESFJ": [
        "I take care of people's practical needs and make sure everyone feels included.",
        "I organize social events and maintain community connections.",
        "I provide emotional support and practical help in equal measure.",
        "I value cooperation, tradition, and social responsibility.",
    ],
    "ISTP": [
        "I analyze problems hands-on and find practical, efficient solutions.",
        "I stay calm under pressure and adapt to changing situations.",
        "I prefer action over theory — show me how it works in practice.",
        "I value independence and the freedom to solve problems my way.",
    ],
    "ESTP": [
        "I thrive on immediate action and adapt quickly to any situation.",
        "I read people and situations instantly and respond in real time.",
        "I prefer hands-on engagement over abstract discussion.",
        "I take calculated risks and learn from experience.",
    ],
    "ISFP": [
        "I express myself through creative action rather than analytical words.",
        "I live in the present moment and appreciate sensory experiences deeply.",
        "I value personal freedom and authentic self-expression.",
        "I connect with others through shared experiences, not abstract ideas.",
    ],
    "ESFP": [
        "I light up any room and bring energy and enthusiasm to every situation!",
        "I live for the moment and seek exciting new experiences.",
        "I connect with people through fun, warmth, and spontaneity.",
        "I learn by doing, not by reading or analyzing.",
    ],
}


def run_mbti_calibration(provider_factory):
    """Run all 64 MBTI prompts, measure WEAKEN/STRENGTHEN/REJECT per type."""
    print("MBTI Calibration — 16 Types × 4 Prompts")
    print("=" * 60)

    results = {}
    for mbti_type, prompts in MBTI_PROMPTS.items():
        eng = CognitiveRuntimeEngine(llm_provider=provider_factory())
        eng.start()
        ad = DialogAdapter()
        weaken_total = 0
        strengthen_total = 0
        reject_total = 0

        for i, prompt in enumerate(prompts):
            eng.on_event(ad.adapt(prompt, mbti_type, i + 1))
            m = eng._trace_v3.meta_analyze()
            rd = m.get("reason_distribution", {})
            weaken_total = rd.get("weaken", 0)
            strengthen_total = rd.get("strengthen", 0)
            reject_total = rd.get("reject", 0)

        results[mbti_type] = {
            "weaken": weaken_total,
            "strengthen": strengthen_total,
            "reject": reject_total,
            "ratio": strengthen_total / max(1, weaken_total),
        }

    # Analyze by dimension
    T_types = ["INTJ", "ENTJ", "INTP", "ENTP", "ISTJ", "ESTJ", "ISTP", "ESTP"]
    F_types = ["INFJ", "ENFJ", "INFP", "ENFP", "ISFJ", "ESFJ", "ISFP", "ESFP"]
    E_types = [t for t in results if t[0] == 'E']
    I_types = [t for t in results if t[0] == 'I']

    def avg_weaken(types):
        vals = [results[t]["weaken"] for t in types if t in results]
        return np.mean(vals) if vals else 0

    T_weaken = avg_weaken(T_types)
    F_weaken = avg_weaken(F_types)
    d_TF = (F_weaken - T_weaken) / max(np.std(list(results[t]["weaken"] for t in results.values())), 1e-6)

    print(f"\n  T-types (Thinking):  avg WEAKEN={T_weaken:.1f}")
    print(f"  F-types (Feeling):   avg WEAKEN={F_weaken:.1f}")
    print(f"  T/F Cohen's d:       {d_TF:.2f} {'✅ significant' if abs(d_TF) >= 0.8 else '⚠️ moderate' if abs(d_TF) >= 0.5 else '❌ weak'}")

    # Top/bottom
    sorted_types = sorted(results.items(), key=lambda x: x[1]["weaken"])
    print(f"\n  Lowest WEAKEN (best aligned): {sorted_types[:3]}")
    print(f"  Highest WEAKEN (most conflict): {sorted_types[-3:]}")

    os.makedirs("data/monitor", exist_ok=True)
    with open("data/monitor/mbti_calibration.json", "w") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    def make_prov():
        return OpenAIProvider("deepseek", {
            "api_key": KEY,
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
        })

    run_mbti_calibration(make_prov)
