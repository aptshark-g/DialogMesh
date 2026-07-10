# Plan: metacognition_fusion_loop

## Stage 1: l2_summary_rebuild
- Rebuild `core/agent/v3_2/l2_summary/l2_summary.py` with data models and `L2SummaryAggregator`
- Keep backward compatibility (`build_daily_report`, deprecated `L2SummaryEntry`)
- Target: ~250-300 lines

## Stage 2: embedding_architecture_split
- Split `core/agent/v3_2/embedding/behavior_embedding.py` into 8 modules
- Create compatibility shim, update `__init__.py`
- Target: ~30-60 lines per module

## Stage 3: metacognition_fusion_loop
- Modify `metacognition.py`, `fusion/fusion_engine.py`, `integration.py`
- Implement closed-loop metacognition → fusion
- Target: ~80 lines of changes

## Stage 4: Verification
- `python -m py_compile` on all modified/created files
- Report file list and line counts
