# Plan: v3.2 DialogMesh Module Completion

## Stage 1 — behavior_graph_stats
- [ ] Create `core/agent/v3_2/behavior_graph/statistics.py` (GraphStatisticsCollector)
- [ ] Update `graph_store.py` — add `get_chain()`, `get_edges_for_chain()`, update stats after ops
- [ ] Update `pruning.py` — set `last_prune_time`
- [ ] Update `__init__.py` — export new classes

## Stage 2 — predictor_training_loop
- [ ] Rewrite `training_loop.py` (~80-100 lines, TrainingFeedbackLoop)

## Stage 3 — rewarder_abl_noise
- [ ] Rewrite `abl_reflection.py` — add LLM path, to_dict
- [ ] Rewrite `noise_adaptation.py` — effectiveness, signal strength, get_effective_reward
- [ ] Update `rewarder.py` — wire new features, extract methods, pass has_alternative

## Stage 4 — causal_substrate_graph
- [ ] Update `causal_substrate.py` — real graph traversal, update_edge_prior
- [ ] Update `skeleton_matcher.py` — expand mappings, extract_from_behavior_step
- [ ] Update `delta_adjuster.py` — apply_to_edge, apply_to_graph

## Stage 5 — do_calculus_rules
- [ ] Create `do_calculus.py` — DoCalculusEngine with 3 rules + identify
- [ ] Create `frontdoor_criterion.py` — FrontdoorCriterion
- [ ] Create `d_separation.py` — DSeparator
- [ ] Update `validator.py` — use DoCalculusEngine.identify(), auto-downgrade
- [ ] Update `__init__.py` — export new classes

## Stage 6 — Verification
- [ ] Run `python -m py_compile` on all modified/created files
- [ ] Report line counts
