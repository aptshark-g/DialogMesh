"""Stage 3: MacroMicroQuantizer ? ????????"""
import math
from typing import List
from .models import EDU, CohesionScore, DiscourseEntity

# ?????? (??? TiMem ?????)
MACRO_WEIGHTS = {
    "cosine_sim": 0.35,
    "intent_match": 0.25,
    "entity_overlap": 0.20,
    "predicate_consistency": 0.20,
}

# ?????? (??? LCseg ???)
MICRO_WEIGHTS = {
    "entity_jaccard": 0.30,
    "causal_chain": 0.25,
    "attribution_consistency": 0.25,
    "predicate_transition": 0.20,
}


def _compute_entity_jaccard(e1: List[str], e2: List[str]) -> float:
    """Jaccard ???"""
    s1, s2 = set(e1), set(e2)
    if not s1 and not s2:
        return 0.5
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


class MacroMicroQuantizer:
    """
    ??-????????
    macro (0.6): ???????
    micro (0.4): ??-??-????
    ?? score > 0.75 -> continue; < 0.25 -> fork; ?? -> gray_zone
    """

    def score_pair(self, left: EDU, right: EDU) -> CohesionScore:
        """?????? EDU ??????"""
        # ????: ??????????
        macro = self._macro_score(left, right)

        # ????: ??-??-????
        micro = self._micro_score(left, right)

        return CohesionScore(
            left_index=left.index,
            right_index=right.index,
            macro_score=macro,
            micro_score=micro,
        )

    def score_all(self, edus: List[EDU]) -> List[CohesionScore]:
        """???????? EDU ?????"""
        return [self.score_pair(edus[i], edus[i+1]) for i in range(len(edus)-1)]

    def _macro_score(self, left: EDU, right: EDU) -> float:
        """???????"""
        score = 0.0

        # ?????
        subject_match = 1.0 if left.subject and right.subject and left.subject == right.subject else 0.0
        if not left.subject or not right.subject:
            subject_match = 0.5  # ????????

        # ?????
        pred_match = 1.0 if left.predicate and right.predicate and left.predicate == right.predicate else 0.0
        if not left.predicate or not right.predicate:
            pred_match = 0.5

        # ????
        entity_overlap = _compute_entity_jaccard(left.entities, right.entities)

        # ????? (??/??/??????????)
        intent_shift = 0.0
        if left.imperative != right.imperative or left.question != right.question:
            intent_shift = 0.3
        if left.negation != right.negation:
            intent_shift += 0.15

        score = (
            MACRO_WEIGHTS["cosine_sim"] * (subject_match * 0.5 + pred_match * 0.5)
            + MACRO_WEIGHTS["intent_match"] * (1.0 - intent_shift)
            + MACRO_WEIGHTS["entity_overlap"] * entity_overlap
            + MACRO_WEIGHTS["predicate_consistency"] * pred_match
        )
        return max(0.0, min(1.0, score))

    def _micro_score(self, left: EDU, right: EDU) -> float:
        """????-????"""
        entity_jaccard = _compute_entity_jaccard(left.entities, right.entities)

        # ?????: ??? = ???
        causal = 1.0 if left.obj and right.subject and left.obj == right.subject else 0.0

        # ?????
        attr_consistency = 0.5
        if left.negation == right.negation:
            attr_consistency += 0.25
        if left.question == right.question:
            attr_consistency += 0.25

        # ????: ??/????????
        pred_trans = 1.0 if left.predicate and right.predicate and left.predicate == right.predicate else 0.0

        score = (
            MICRO_WEIGHTS["entity_jaccard"] * entity_jaccard
            + MICRO_WEIGHTS["causal_chain"] * causal
            + MICRO_WEIGHTS["attribution_consistency"] * attr_consistency
            + MICRO_WEIGHTS["predicate_transition"] * pred_trans
        )
        return max(0.0, min(1.0, score))

    def classify_quadrant(self, macro: float, micro: float) -> str:
        """
        ?????:
        macro>0.7, micro>0.7 -> strong_continue (??????)
        macro>0.7, micro<0.5 -> semantic_shift (??????)
        macro<0.5, micro>0.7 -> entity_drift (?????????)
        macro<0.5, micro<0.5 -> fork (???)
        """
        if macro >= 0.7 and micro >= 0.7:
            return "strong_continue"
        if macro >= 0.7 and micro < 0.5:
            return "semantic_shift"
        if macro < 0.5 and micro >= 0.7:
            return "entity_drift"
        return "fork"


QUANTIZER = MacroMicroQuantizer()
