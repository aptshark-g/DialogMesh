# Literature Cortex — Parameter Registry Specification

> Version: 1.0  
> Source: `lcortex/unified/registry.py`  
> Total Parameters: 20+  
> For DialogMesh cross-project alignment.

---

## Parameter Schema

```json
{
  "key": "verification.min_trust_score",
  "value": 0.1,
  "type": "float",
  "description": "zhun ru zui xiao xin ren fen",
  "min": 0.0,
  "max": 1.0,
  "adaptive": true
}
```

---

## Verification Layer Parameters

| Key | Default | Type | Range | Adaptive | Description |
|-----|---------|------|-------|----------|-------------|
| `verification.min_trust_score` | 0.1 | float | [0.0, 1.0] | Yes | zhun ru zui xiao xin ren fen. Content below this is rejected. |
| `verification.fast_max_length` | 500 | int | — | No | FAST mode max text length (chars) |
| `verification.slow_min_length` | 2000 | int | — | No | SLOW mode min text length (chars) |
| `verification.spam_density_threshold` | 0.03 | float | [0.0, 1.0] | No | Spam keyword density threshold |

---

## Prescreen Parameters

| Key | Default | Type | Range | Adaptive | Description |
|-----|---------|------|-------|----------|-------------|
| `prescreen.quality_fast_threshold` | 0.6 | float | [0.0, 1.0] | No | Quality score for FAST path |
| `prescreen.quality_skip_threshold` | 0.25 | float | [0.0, 1.0] | No | Quality score for SKIP path |
| `prescreen.emotion_slow_threshold` | 0.7 | float | [0.0, 1.0] | No | Emotion score triggering SLOW |

---

## Fusion Engine Parameters

| Key | Default | Type | Range | Adaptive | Description |
|-----|---------|------|-------|----------|-------------|
| `fusion.min_paths_for_full` | 3 | int | [1, 4] | No | Min valid verification paths for full verdict |
| `fusion.path_penalty_2` | 0.3 | float | [0.0, 1.0] | No | Penalty when valid paths < 2 |
| `fusion.path_penalty_3` | 0.7 | float | [0.0, 1.0] | No | Penalty when valid paths < 3 |

---

## Feedback Loop Parameters

| Key | Default | Type | Range | Adaptive | Description |
|-----|---------|------|-------|----------|-------------|
| `feedback.correction_rate_alert` | 0.30 | float | [0.0, 1.0] | Yes | Alert threshold for correction rate |
| `feedback.min_samples_adjust` | 10 | int | — | No | Min samples before threshold adjustment |
| `feedback.threshold_step` | 0.05 | float | [0.0, 0.2] | No | Step size for threshold adjustment |

---

## Domain Strategy Parameters

| Key | Default | Type | Description |
|-----|---------|------|-------------|
| `domain.strategy.physics` | FORMAL | enum | Physics/math domain: formal verification |
| `domain.strategy.medicine` | EMPIRICAL | enum | Medicine/biology: empirical evidence |
| `domain.strategy.tcm` | DIALECTIC | enum | TCM/psychology: dialectic reasoning |

**Strategy Types:**
- `FORMAL` — Mathematical/physical propositions. Requires proof or derivation.
- `EMPIRICAL` — Medical/biological claims. Requires experimental evidence.
- `DIALECTIC` — Humanistic/experiential domains. Requires balanced pro/con analysis.
- `HYBRID` — Mixed domains. Weighted combination of above.

---

## DialogMesh Integration Interface

```python
from lcortex.unified.registry import ParameterRegistry

reg = ParameterRegistry()

# Get parameter
score = reg.get("verification.min_trust_score")  # → 0.1

# Set parameter (with type/range checking)
ok = reg.set("verification.min_trust_score", 0.15)  # → True
bad = reg.set("verification.min_trust_score", "high")  # → False

# List by prefix
verify_params = reg.list_params("verification.")
# → {verification.min_trust_score: ParamDef, ...}

# Persist to UnifiedStore
reg.save_to_store(store)

# Load from UnifiedStore
reg.load_from_store(store)
```

---

## Persistence Schema (SQLite)

```sql
CREATE TABLE parameters (
    param_key TEXT PRIMARY KEY,
    param_value TEXT,        -- JSON-encoded
    param_type TEXT,         -- str | int | float | bool | enum
    description TEXT,
    updated_at REAL
);
```

---

## Cross-Project Alignment Notes

| DialogMesh Concept | Cortex Equivalent | Alignment Status |
|-------------------|-------------------|-----------------|
| BeliefState.threshold | `verification.min_trust_score` | Direct map |
| PrecisionMode.fast | `prescreen.quality_fast_threshold` | Direct map |
| DomainStrategy.formal | `domain.strategy.physics` | Direct map |
| CorrectionRate | `feedback.correction_rate_alert` | Direct map |
