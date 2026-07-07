from .models import TrainingSignal

class TrainingFeedbackLoop:
    def __init__(self, rewarder=None):
        self.rewarder = rewarder

    def on_user_action(self, prediction, actual, actual_type, is_correction=False):
        signal = TrainingSignal(prediction.candidates, actual, is_correction=is_correction)
        signal.compute_reward()
        if is_correction: signal.reward = -0.20
        if self.rewarder:
            try:
                self.rewarder.on_reward(signal)
            except AttributeError:
                pass  # reward method not available
        return signal