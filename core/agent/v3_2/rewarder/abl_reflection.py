from .models import ABLReflection
import time

class ABLReflectionGenerator:
    ERROR_TYPES = ["over_generalization", "missing_step", "wrong_entity", "domain_mismatch"]

    def generate(self, edge_key, predicted, actual, ctx="", turn=0):
        et = "wrong_entity"
        if predicted and actual and predicted[:2] == actual[:2]: et = "missing_step"
        return ABLReflection(edge_key, et, actual, "", "", turn, time.time())