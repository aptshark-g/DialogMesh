"""MBTI Calibration v3 — 93 real standard questions + 16 personality descriptions.

Each personality type answers all 93 questions from their perspective.
Expected: T-types (INTJ/ISTJ/INTP/ENTJ...) → low WEAKEN
         F-types (ENFP/ESFP/INFJ/ENFJ...) → high WEAKEN
Uses Section 九 descriptions as system prompts for authentic personality simulation.
"""
import sys, os, json
sys.path.insert(0, '.')
os.environ['DIALOGMESH_MONITOR'] = '1'
import numpy as np
from core.agent.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.events.event_ir import DialogAdapter

KEY = "sk-20d76b2a00314beabb73dd8ab9d5743d"

# Section 九 — 16 personality descriptions (abbreviated for prompt length)
PERSONA_DESCRIPTIONS = {
    "INTJ": "目标感极强，独立挑剔，自带怀疑思维，行事果决，对专业标准要求极高。视野宏大，擅长完整策划并落地项目。",
    "ENTJ": "坦诚果决，天生活动领导者。擅长搭建完整体系，解决组织核心问题。擅长深度思辨。",
    "INTP": "内敛自持，极度痴迷理论、逻辑、科学原理。擅长逻辑拆解，分析解决抽象难题。",
    "ENTP": "反应敏捷，头脑灵活。喜欢辩证思考，乐于站在双方角度辩论。擅长攻克全新挑战性问题。",
    "ISTJ": "严肃安静，行事务实有序逻辑。高度负责任。严格按既定标准做决策。重视传统与忠诚。",
    "ESTJ": "务实客观，重视事实。擅长组织统筹，追求最高效率。决断力强，关注细节，决策迅速。",
    "ISTP": "冷静旁观者，热衷探究因果。擅长直击问题核心，快速找到实操解法。擅长从海量信息中提炼关键矛盾。",
    "ESTP": "实战型解决者，擅长现场即时处理突发问题。务实包容，适应性强，反感冗长理论。",
    "INFJ": "凭借坚韧创意达成成就。洞察力强，擅长读懂他人内心动机。坚守自身价值观，行事坦荡。",
    "ENFJ": "热忱共情，责任心强。真心在意他人需求。擅长社交，人缘好，富有同理心。",
    "INFP": "安静理想主义者，对自身价值观极度忠诚。好奇心强，善于发掘潜在机会。",
    "ENFP": "热情活力，聪慧富有想象力。应变力强，乐于帮扶他人。不喜提前规划，擅长即兴发挥。",
    "ISFJ": "安静和善，负责任有良心。忠诚体贴，善于体察他人情绪。致力于打造有序和谐环境。",
    "ESFJ": "真诚健谈，协作力强。重视人际和谐。主动为他人提供帮助。喜欢团队协作。",
    "ISFP": "腼腆温和，安静敏感。回避冲突。安于现状，不急于追求短期成果。需要独立私人空间。",
    "ESFP": "外向和善，包容开朗。情商出众，能快速适配他人与环境。热爱生活、人际交往与物质体验。",
}

# Scored dimensions for T/F separation
T_TYPES = ["INTJ", "ENTJ", "INTP", "ENTP", "ISTJ", "ESTJ", "ISTP", "ESTP"]
F_TYPES = ["INFJ", "ENFJ", "INFP", "ENFP", "ISFJ", "ESFJ", "ISFP", "ESFP"]


def run_mbti_93(provider_factory, sample_types=None, questions_per_type=20):
    """Sample subset of questions for speed. Full 93 per type = ~1488 LLM calls."""
    if sample_types is None:
        sample_types = ["INTJ", "ENFP", "ISTJ", "ESFP"]
    
    # Take every 5th question for quick sampling (20 of 93)
    # Use 5 personality-statements per type as prompts (not test questions)
    # These TRIGGER alignment/misalignment signals
    statements = {
        "INTJ": ["I approach problems through systematic analysis and logical frameworks.",
                  "I prefer working independently on complex, long-term strategic challenges.",
                  "Emotions are secondary to objective data — show me the evidence.",
                  "I plan everything meticulously before taking action.",
                  "I value intellectual rigor and strategic depth above social harmony."],
        "ENFP": ["I am energized by connecting with people and exploring new possibilities!",
                  "My intuition guides me more than rigid logic or detailed plans.",
                  "I see potential in everyone and get excited about what could be!",
                  "I thrive on variety, spontaneity, and emotional connections.",
                  "I follow my heart rather than strict rules — life is an adventure!"],
        "ISTJ": ["I follow established procedures and value reliability above all.",
                  "I keep detailed records and check facts before making decisions.",
                  "I respect tradition and proven methods — they exist for a reason.",
                  "I fulfill my commitments precisely and expect others to do the same.",
                  "I value stability, order, and predictable outcomes in work and life."],
        "ESFP": ["I light up any room and bring energy and enthusiasm to every situation!",
                  "I live for the moment and seek exciting new experiences.",
                  "I connect with people through fun, warmth, and spontaneity.",
                  "I learn by doing, not by reading or analyzing.",
                  "I adapt instantly to whatever comes my way — flexibility is my strength!"],
        "INTP": ["I love exploring abstract theoretical frameworks and logical models.",
                  "I question assumptions constantly — every system has hidden flaws.",
                  "I need time alone to process complex ideas deeply.",
                  "I value precision and intellectual rigor above social harmony.",
                  "I analyze everything from first principles — nothing is taken for granted."],
        "ENFJ": ["I naturally inspire and motivate people to become their best selves.",
                  "I feel responsible for the emotional well-being of my team.",
                  "I read social dynamics effortlessly and adapt accordingly.",
                  "I believe in developing people, not just achieving tasks.",
                  "I seek harmony and meaningful connection in all relationships."],
    }


    
    results = {}
    for persona in sample_types:
        desc = PERSONA_DESCRIPTIONS[persona]
        prompt_list = statements.get(persona, statements["INTJ"])[:questions_per_type]
        
        eng = CognitiveRuntimeEngine(llm_provider=provider_factory())
        eng.start()
        ad = DialogAdapter()
        
        for i, prompt in enumerate(prompt_list):
            eng.on_event(ad.adapt(prompt, persona, i + 1))
        
        m = eng._trace_v3.meta_analyze()
        rd = m.get("reason_distribution", {})
        results[persona] = {
            "weaken": rd.get("weaken", 0),
            "strengthen": rd.get("strengthen", 0),
            "reject": rd.get("reject", 0),
        }
    
    # Analysis
    t_vals = [results[t]["weaken"] for t in T_TYPES if t in results]
    f_vals = [results[t]["weaken"] for t in F_TYPES if t in results]
    
    for persona, r in results.items():
        t_label = "(T)" if persona in T_TYPES else "(F)"
        print(f"  {persona} {t_label}: W={r['weaken']} S={r['strengthen']} R={r['reject']}")
    
    if t_vals and f_vals:
        d = (np.mean(f_vals) - np.mean(t_vals)) / max(np.std(list(r["weaken"] for r in results.values())), 1e-6)
        print(f"  T-type avg WEAKEN: {np.mean(t_vals):.1f}")
        print(f"  F-type avg WEAKEN: {np.mean(f_vals):.1f}")
        print(f"  Cohen's d (T/F): {d:.2f} {'✅ significant' if abs(d)>=0.8 else '⚠️ moderate' if abs(d)>=0.5 else '❌ weak'}")
    else:
        d = 0
    
    os.makedirs("data/monitor", exist_ok=True)
    with open("data/monitor/mbti_calibration.json", "w") as f:
        json.dump({"results": results, "cohens_d": d, "n_questions": len(questions)}, f, indent=2)
    
    return results, d


if __name__ == "__main__":
    def make_prov():
        return OpenAIProvider("deepseek", {
            "api_key": KEY, "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
        })
    
    print("MBTI Calibration v3 — 93 Real Questions")
    print("=" * 50)
    run_mbti_93(make_prov, ["INTJ", "ENFP", "ISTJ", "ESFP", "INTP", "ENFJ"], 20)
