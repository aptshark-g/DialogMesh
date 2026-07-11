class CognitiveLoadEstimator:
    LOAD_MAP = {
        "TOOL_EXEC": 0.2, "CODE_RUN": 0.3, "LOG_CHECK": 0.1,
        "ENTITY_ANALYZE": 0.4, "CONFIG_MODIFY": 0.3, "EXPLORATION": 0.3,
    }
    DEFAULT_LOAD = 0.3

    def estimate(self, action_type: str):
        return self.LOAD_MAP.get(action_type, self.DEFAULT_LOAD)

    def adjust_by_turn(self, load: float, turn: int):
        return min(1.0, load + min(0.3, turn * 0.01))