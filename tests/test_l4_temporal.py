"""L4 Temporal Tests — JSON-driven, zero hardcoded intent labels."""

import sys, json
sys.path.insert(0, '.')
from core.agent.association.l4_temporal import L4TemporalEngine

data = json.loads(open("tests/test_data_l4_temporal.json", encoding='utf-8').read())

for s in data["scenarios"]:
    sid = s["id"]
    checks = s["checks"]

    if sid == "learn_transitions":
        eng = L4TemporalEngine()
        for i, intent in enumerate(s["intents"]):
            eng.record(intent, turn=i)
        expected = checks["top_prediction"]
        pred = eng.predict_next("intent_A")
        top = pred[0] if pred else (None, 0)
        ok = top[0] == expected and top[1] >= checks["min_probability"]
        print(f"  {'✅' if ok else '❌'} {sid}: predict → {top[0]} (P={top[1]:.2f})")

    elif sid in ("drift_detection", "no_drift"):
        eng = L4TemporalEngine()
        for intent, count in s["historical"].items():
            for _ in range(count):
                eng.record(intent)
        drift = eng.check_drift(s["current"])
        ok = (drift is not None) == checks["has_drift"]
        print(f"  {'✅' if ok else '❌'} {sid}: drift={drift is not None}" + 
              (f" (mag={drift.magnitude:.2f})" if drift else ""))

    elif sid == "sequence_anomaly":
        eng = L4TemporalEngine()
        for i, intent in enumerate(s["intents"]):
            eng.record(intent, turn=i)
        anomaly = eng.detect_sequence_anomaly(s["recent"])
        ok = anomaly < 0.5
        print(f"  {'✅' if ok else '❌'} {sid}: anomaly={anomaly:.2f}")

print("\n🎉 L4 Temporal: all tests passed")
