# Hybrid Self-evolving Structured Memory for GUI Agents (HyMEM)

Official implementation for the paper **"Hybrid Self-evolving Structured Memory for GUI Agents"**.

`HyMEM` is a brain-inspired memory system for GUI agents that combines:
- **Continuous trajectory embeddings** for fine-grained multimodal evidence,
- **Discrete symbolic strategies/tags** for high-level reasoning,
- **Graph-structured retrieval** for multi-hop, diverse memory access,
- **Online self-evolving updates** for long-horizon task execution.

Main results from the paper show:
- **+22.5% absolute improvement** for Qwen2.5-VL-7B (12.5% -> 35.0%),
- performance surpassing strong closed-source APIs including Gemini2.5-Pro-Vision and GPT-4o in the reported setup.

<p align="center">
  <img src="CoMEM-Agent-Inference/media/main_figure.png" alt="HyMEM overview" width="100%">
</p>

## Paper

- Title: **Hybrid Self-evolving Structured Memory for GUI Agents**
- Authors: **Sibo Zhu, Wenyi Wu, Kun Zhou, Stephen Wang, Biwei Huang**

## Repository Layout

This repository contains two major components:

- `CoMEM-Agent-Inference`: inference/evaluation pipeline for MMInA, Mind2Web, and WebVoyager
- `CoMEM-Agent-train`: training code for continuous memory encoder (Q-Former + LoRA)

## Environment Setup

From repository root:

```bash
conda create -n hymem python=3.10 -y
conda activate hymem

pip install -r requirements.txt
pip install -r CoMEM-Agent-Inference/requirements_web.txt

playwright install
```

## Model Serving

By default, inference expects OpenAI-compatible endpoints:
- Agent VLM (`qwen2.5-vl`) at `http://localhost:8000/v1`
- Grounding model (`ui-ins-7b`) at `http://localhost:8006/v1`

Model-to-endpoint mapping is defined in `CoMEM-Agent-Inference/agent/llm_config.py`.

For a full Docker + vLLM setup, see `DOCKER_SETUP.md`.

## Build HyMEM Graph Memory Index

Before using graph memory, build an index from successful trajectories:

```bash
cd CoMEM-Agent-Inference

python -m graph_memory.build_graph_from_trajectories \
  --memory_data_dir "data/trajectories" \
  --output_path "graph_index/all_domains" \
  --model qwen2.5-vl \
  --tag_cache_path "graph_memory_cache/tags.json" \
  --summary_cache_path "graph_memory_cache/summaries.json"
```

Notes:
- The builder only reads trajectory files under `success/` folders.
- VLM-based deduplication is enabled by default during graph construction.

## Reproduce HyMEM Inference (WebVoyager)

The following command enables the full hybrid setup, including:
- local working-memory refresh (`--use_dynamic_memory_update`)
- global graph self-evolution (`--use_self_evolving_memory`)

```bash
bash CoMEM-Agent-Inference/scripts/runners/run_agent.sh \
  --eval_type webvoyager \
  --domain Amazon \
  --model qwen2.5-vl \
  --tool_model_name qwen2.5-vl \
  --use_continuous_memory \
  --checkpoint_path "/path/to/checkpoints/lora_qformer_test_V4-700_merged" \
  --use_graph_memory \
  --graph_memory_index_path "graph_index/all_domains" \
  --graph_similar_num 10 \
  --graph_expand_hops 1 \
  --use_dynamic_memory_update \
  --collect_training_data \
  --save_examples_memory \
  --use_self_evolving_memory \
  --graph_persist_interval 5 \
  --memory_data_dir "/path/to/trajectories" \
                    "/path/to/mind2web" \
                    "/path/to/guiact_converted" \
  --result_dir "results/ablation_hybrid_graph_memory"
```

You can also pass multiple `--memory_data_dir` flags if preferred.

Important:
- In current code, global self-evolving insertion is triggered only when successful trajectories are saved, so `--collect_training_data` and `--save_examples_memory` are required together with `--use_self_evolving_memory`.

## Core Memory Flags

- `--use_discrete_memory`: retrieve and summarize textual takeaways from trajectories
- `--use_continuous_memory`: inject learned continuous trajectory embeddings (Q-Former checkpoint)
- `--use_graph_memory`: retrieve from graph index with expansion/diversity
- `--use_dynamic_memory_update`: refresh working memory during execution
- `--use_self_evolving_memory`: online self-evolving graph updates from successful trajectories

For full CLI options:

```bash
bash CoMEM-Agent-Inference/scripts/runners/run_agent.sh --help
```

## Benchmarks

Supported evaluation types:
- `mmina`
- `mind2web`
- `mind2web_executable`
- `webvoyager`

Main entrypoint:
- `CoMEM-Agent-Inference/scripts/runners/run_agent.sh`

Additional examples:
- `CoMEM-Agent-Inference/scripts/runners/run_webvoyager.sh`
- `CoMEM-Agent-Inference/scripts/runners/run_mind2web.sh`
- `CoMEM-Agent-Inference/scripts/runners/run_with_continuous_memory.sh`

## Training Continuous Memory (Q-Former + LoRA)

Training scripts are under `CoMEM-Agent-train/scripts`:

```bash
bash CoMEM-Agent-train/scripts/prepare_mds_data.sh
bash CoMEM-Agent-train/scripts/finetune_lora_vision_test.sh
bash CoMEM-Agent-train/scripts/merge_lora.sh
```

Important:
- These scripts currently contain machine-specific absolute paths.
- Edit paths (data/checkpoints/cache) before running on a new machine.

## Citation

If you use this repository, please cite:

```bibtex
@misc{zhu2026hymem,
  title={Hybrid Self-evolving Structured Memory for GUI Agents},
  author={Sibo Zhu and Wenyi Wu and Kun Zhou and Stephen Wang and Biwei Huang},
  year={2026},
  note={Manuscript}
}
```
