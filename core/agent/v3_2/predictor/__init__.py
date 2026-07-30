"""v3.2 predictor → merged to core.agent.predictor"""
from core.agent.predictor.predictor import BehaviorPredictor
from core.agent.predictor.models import Candidate, PredictionResult, TrainingSignal
from core.agent.predictor.training_loop import TrainingFeedbackLoop
from core.agent.predictor.candidate_generator import CandidateGenerator
