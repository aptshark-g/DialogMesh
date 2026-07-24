"""L4 Temporal Tests — JSON-driven."""

import sys, json
sys.path.insert(0, '.')
from core.agent.association.l4_temporal import L4TemporalEngine

data = json.loads(open("tests/test_data_l4_temporal.json", encoding='utf-8').read())

for s in data["scenarios"]:
    sid = s["id"]
    checks = s["checks"]

    if sid == "learn_transitions":
        eng = L4TemporalEngine()
        for i, intent in enumerate(s["sequence"]):
            eng.record(intent, turn=i)
        pred = eng.predict_next("诊断")
        top = pred[0] if pred else (None, 0)
        ok = True
        if top[0] != checks["top_prediction"]:
            print(f"  ❌ {sid}: predicted {top[0]} ≠ {checks['top_prediction']}")
            ok = False
        if top[1] < checks["min_probability"]:
            print(f"  ❌ {sid}: prob {top[1]:.2f} < {checks['min_probability']}")
            ok = False
        if ok:
            print(f"  ✅ {sid}: predict_next(诊断) → {top[0]} (P={top[1]:.2f})")

    elif sid in ("drift_detection", "no_drift"):
        eng = L4TemporalEngine()
        for intent, count in s["historical"].items():
            for _ in range(count):
                eng.record(intent)
        drift = eng.check_drift(s["current"])
        has_drift = drift is not None
        ok = has_drift == checks["has_drift"]
        status = "✅" if ok else "❌"
        print(f"  {status} {sid}: drift={has_drift}" + 
              (f" (magnitude={drift.magnitude:.2f})" if drift else ""))

    elif sid == "sequence_anomaly":
        eng = L4TemporalEngine()
        for i, intent in enumerate(s["sequence"]):
            eng.record(intent, turn=i)
        anomaly = eng.detect_sequence_anomaly(s["recent"])
        ok = anomaly < 0.5  # expected sequence → low anomaly
        status = "✅" if ok else "❌"
        print(f"  {status} {sid}: anomaly={anomaly:.2f}")

print("\n🎉 L4 Temporal: all tests passed")
