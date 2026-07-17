# Quality Metrics — Literature-Supported Formulas

## 1. COGNITIVE ARCHITECTURE METRICS

### 1.1 Reflection Improvement Rate (Reflexion, Shinn et al. 2023)
Source: https://arxiv.org/abs/2303.11366
Metric: task accuracy before vs after reflection episode
```
RIR = (post_reflection_accuracy - pre_reflection_accuracy) / pre_reflection_accuracy
Range: [-1, ∞), positive = improvement
Experiment: Same task, run without MetaConsumer → run with MetaConsumer → compare
```

### 1.2 Self-Refine Delta (Madaan et al., 2023)
Source: https://arxiv.org/abs/2303.17651
Metric: quality improvement per iteration
```
SRD = quality(turn_n) - quality(turn_{n-1})
aggregated: mean(SRD) over all consecutive pairs
Experiment: Track response quality scores across consecutive turns
```

### 1.3 Learning Rate (Agent Hospital, Tsinghua 2024)
Source: https://arxiv.org/abs/2405.02957
Metric: performance gain over time
```
LR = (score_turn_N - score_turn_1) / N
Range: [-1, 1], positive = learning
Experiment: Compare Mind stats at turn 1 vs turn 20
```

## 2. EPISTEMIC AGENCY METRICS

### 2.1 Error Detection Rate (ReflectionBench, ICML 2025)
Source: https://arxiv.org/abs/2502.04476
Metric: detected errors / total errors
```
EDR = |correctly_detected_errors| / |total_induced_errors|
Experiment: Inject known errors → check if MetaConsumer warns
```

### 2.2 Correction Success Rate
```
CSR = |errors_corrected_after_detection| / |detected_errors|
Experiment: After detection, does policy change lead to correct answer?
```

### 2.3 Confidence Calibration Error (Guo et al., 2017)
Source: https://arxiv.org/abs/1706.04599
Metric: |confidence - accuracy|
```
ECE = Σ |B_m|/N * |acc(B_m) - conf(B_m)|
B_m = confidence bins, acc = actual correctness
Experiment: Compare transition confidence vs actual response quality
```

## 3. PERSONALITY DISCRIMINATION

### 3.1 Cohen's d (effect size for group separation)
Source: Standard statistical metric
Metric: (mean_INTJ - mean_ENFP) / pooled_stddev
```
d = (μ_A - μ_B) / σ_pooled
d ≥ 0.8: large effect (good discrimination)
d = 0.5: medium; d = 0.2: small
Experiment: ENFP_WEAKEN vs INTJ_WEAKEN
```

## 4. CONTROLLED EXPERIMENT DESIGN

### Experiment 1: Mind ON vs OFF
```
Treatment:  Mind enabled (with prior learning)
Control:    Mind disabled (fresh start)
Task:       10 turns: 5 normal + 5 topic switch
Metric:     WEAKEN count in treatment vs control
Hypothesis: Mind should reduce WEAKEN by pre-activating stable relations
Expected:   d = (WEAKEN_off - WEAKEN_on) / σ > 0.5
```

### Experiment 2: REJECT Detection
```
Treatment:  REJECT transition enabled
Control:    REJECT transition disabled  
Task:       6 turns with 2 rejection sentences injected
Metric:     MetaConsumer warnings in treatment vs control
Hypothesis: Treatment should detect ≥1 REJECT warning
Expected:   EDR > 0.5 (at least one rejection detected)
```

### Experiment 3: Personality Discrimination
```
Task:       INTJ persona 5 turns + ENFP persona 5 turns
Metric:     WEAKEN difference between groups
Formula:    Cohen's d
Hypothesis: ENFP produces more WEAKEN than INTJ
Expected:   d > 0.5 (medium effect)
```

### Experiment 4: DiscourseTree Fork Detection
```
Task:       Same topic 5 turns + topic switch 5 turns
Metric:     Fork count in switch phase vs same-topic phase
Hypothesis: Switch should produce more forks
Expected:   forks_switch > forks_same_topic
```

## 5. IMPLEMENTATION

```python
def controlled_experiment(treatment_fn, control_fn, task, turns=10):
    """Run treatment and control, compare with Cohen's d."""
    treatment_metrics = treatment_fn(task, turns)
    control_metrics = control_fn(task, turns)
    
    mean_t = np.mean(treatment_metrics)
    mean_c = np.mean(control_metrics)
    std_pooled = np.sqrt((np.var(treatment_metrics) + np.var(control_metrics)) / 2)
    
    d = (mean_t - mean_c) / max(std_pooled, 1e-6)
    return {"cohens_d": d, "treatment_mean": mean_t, "control_mean": mean_c}
```
