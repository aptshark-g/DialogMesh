from .models import L1MetaInfo


class MetaInfoExtractor:
    def extract(self, turn, prev_type, prediction=None):
        info = L1MetaInfo()
        info.prev_action = prev_type
        info.current_action = turn.get("action_type", "")
        if prediction:
            info.predicted_next = [c.action_summary for c in getattr(prediction, "top3", [])]
        if turn.get("is_correction"):
            info.correction_detected = True
            info.causal_events.append("USER_CORRECTION")
        if turn.get("is_error"):
            info.causal_events.append("ERROR_TRIGGERED")
        info.associations = turn.get("associations", [])
        info.is_topic_switch = turn.get("is_topic_switch", False)
        info.user_satisfaction = turn.get("sentiment", "neutral")
        return info
