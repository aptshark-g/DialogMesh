"""MBTI Calibration — using real standard test questions.

28-question MBTI form (public domain, from MBTI manual).
Each question maps to a dimension: E/I, S/N, T/F, J/P.
System answers each question, measures WEAKEN/STRENGTHEN per type.
Calibration target: T-types produce < WEAKEN than F-types.
"""
import sys, os, json
sys.path.insert(0, '.')
os.environ['DIALOGMESH_MONITOR'] = '1'
import numpy as np
from core.agent.v4.runtime.engine import CognitiveRuntimeEngine
from core.agent.llm_providers.openai_provider import OpenAIProvider
from core.agent.v4.event_ir import DialogAdapter

KEY = "sk-20d76b2a00314beabb73dd8ab9d5743d"

# Standard MBTI questions (28 items), each answered from a specific type's perspective
MBTI_QUESTIONS = [
    ("E/I", "At a party, do you interact with many people, or stay with a few close friends?"),
    ("E/I", "Do you prefer being the center of attention, or staying in the background?"),
    ("E/I", "Do you think out loud, or process internally before speaking?"),
    ("E/I", "Do you gain energy from socializing, or need alone time to recharge?"),
    ("E/I", "Do you have many acquaintances, or a few deep friendships?"),
    ("E/I", "Do you prefer working in groups, or working alone?"),
    ("E/I", "Do you speak first then think, or think first then speak?"),
    ("S/N", "Do you focus on concrete facts, or on patterns and possibilities?"),
    ("S/N", "Are you more interested in practical applications, or theoretical concepts?"),
    ("S/N", "Do you trust past experience, or trust your intuition about the future?"),
    ("S/N", "Do you prefer step-by-step instructions, or a big-picture overview?"),
    ("S/N", "Are you detail-oriented, or do you focus on the overall vision?"),
    ("S/N", "Do you prefer routine and consistency, or variety and novelty?"),
    ("S/N", "Are you realistic and pragmatic, or imaginative and innovative?"),
    ("T/F", "When making decisions, do you prioritize logic, or consider people's feelings?"),
    ("T/F", "Are you more comfortable giving critical feedback, or offering emotional support?"),
    ("T/F", "Do you value fairness and consistency, or compassion and individual circumstances?"),
    ("T/F", "Is it more important to be truthful, or to be kind?"),
    ("T/F", "Do you analyze problems objectively, or consider the human impact?"),
    ("T/F", "Are you more persuaded by logical arguments, or by emotional appeals?"),
    ("T/F", "Do you prefer clear rules, or flexible guidelines based on context?"),
    ("J/P", "Do you like to plan ahead, or keep options open?"),
    ("J/P", "Do you prefer finishing tasks early, or working best under pressure?"),
    ("J/P", "Do you like having a structured schedule, or going with the flow?"),
    ("J/P", "Are you more comfortable with decisions made, or keeping possibilities open?"),
    ("J/P", "Do you prefer closure and completion, or ongoing exploration?"),
    ("J/P", "Do you like rules and deadlines, or find them restrictive?"),
    ("J/P", "Do you plan your day, or see what happens?"),
]

# Answer each question from 4 representative types
PERSONAS = {
    "INTJ": "Answer as an INTJ: analytical, strategic, independent thinker. Value logic over feelings. Prefer depth over breadth. Plan meticulously.",
    "ENFP": "Answer as an ENFP: enthusiastic, creative, people-oriented. Follow intuition and inspiration. Love possibilities and connections. Spontaneous and warm.",
    "ISTJ": "Answer as an ISTJ: practical, responsible, detail-focused. Trust facts and experience. Follow established procedures. Reliable and thorough.",
    "ESFP": "Answer as an ESFP: outgoing, spontaneous, fun-loving. Live in the moment. Connect through shared experiences. Adaptable and energetic.",
    "INTP": "Answer as an INTP: logical, abstract, theoretical. Question assumptions. Value intellectual precision. Need autonomy to explore ideas.",
    "ENFJ": "Answer as an ENFJ: charismatic, empathetic, inspiring. Naturally lead and develop people. Read social dynamics effortlessly. Value harmony.",
}


def run_mbti_standard(provider_factory, persona_types: list = None, max_questions: int = 14):
    """Run MBTI standard test from given persona types.

    Each persona answers half the questions (14).
    Measures WEAKEN/STRENGTHEN per dimension.
    """
    if persona_types is None:
        persona_types = ["INTJ", "ENFP", "ISTJ", "ESFP"]

    results = {}
    for persona in persona_types:
        system_prompt = PERSONAS[persona]
        questions = MBTI_QUESTIONS[:max_questions]
        
        eng = CognitiveRuntimeEngine(llm_provider=provider_factory())
        eng.start()
        ad = DialogAdapter()
        
        for i, (dim, question) in enumerate(questions):
            full_prompt = f"{system_prompt}\n\nQuestion: {question}"
            eng.on_event(ad.adapt(full_prompt, persona, i + 1))
        
        m = eng._trace_v3.meta_analyze()
        rd = m.get("reason_distribution", {})
        results[persona] = {
            "weaken": rd.get("weaken", 0),
            "strengthen": rd.get("strengthen", 0),
            "reject": rd.get("reject", 0),
            "total_transitions": m["total_transitions"],
        }

    # Analyze T/F dimension
    T_types = ["INTJ", "ISTJ", "INTP"]
    F_types = ["ENFP", "ESFP", "ENFJ"]
    
    t_vals = [results[t]["weaken"] for t in T_types if t in results]
    f_vals = [results[t]["weaken"] for t in F_types if t in results]
    
    if t_vals and f_vals:
        d = (np.mean(f_vals) - np.mean(t_vals)) / max(np.std(list(r["weaken"] for r in results.values())), 1e-6)
    else:
        d = 0
    
    for persona, r in results.items():
        print(f"  {persona}: W={r['weaken']} S={r['strengthen']} R={r['reject']}")
    
    print(f"  T-type avg WEAKEN: {np.mean(t_vals):.1f}" if t_vals else "  No T data")
    print(f"  F-type avg WEAKEN: {np.mean(f_vals):.1f}" if f_vals else "  No F data")
    print(f"  Cohen's d (T/F): {d:.2f} {'✅ significant' if abs(d)>=0.8 else '⚠️ moderate' if abs(d)>=0.5 else '❌ weak'}")
    
    os.makedirs("data/monitor", exist_ok=True)
    with open("data/monitor/mbti_standard.json", "w") as f:
        json.dump({"results": results, "cohens_d": d}, f, indent=2)
    
    return results, d


if __name__ == "__main__":
    def make_prov():
        return OpenAIProvider("deepseek", {
            "api_key": KEY, "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
        })
    
    print("MBTI Standard Calibration — 28 Questions")
    print("=" * 50)
    run_mbti_standard(make_prov, ["INTJ", "ENFP", "ISTJ", "ESFP", "INTP", "ENFJ"])
