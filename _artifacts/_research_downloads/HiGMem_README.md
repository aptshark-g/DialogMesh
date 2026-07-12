# HiGMem

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9](https://img.shields.io/badge/Python-3.9-blue.svg)](https://www.python.org/)

Official reproduction code for **HiGMem: A Hierarchical and LLM-Guided Memory System for Long-Term Conversational Agents**.

The paper uses the name **HiGMem**. Some source files keep the internal development name `fphm`; this is a naming difference only.

## Key Features

- **Hierarchical memory**: organizes long conversations into Turn, Event, and optional Profile layers.
- **LLM-guided memory construction**: incrementally builds structured event memories while reading conversations.
- **Reasoning-aware retrieval**: retrieves candidate events and turns, then filters evidence with LLM judgments.
- **LoCoMo reproduction**: includes the LoCoMo-10 split used by our experiments for convenient reproduction.
- **OpenAI-compatible backend**: supports OpenAI APIs and local OpenAI-compatible services such as vLLM.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Repository Structure](#repository-structure)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Reproducing the Paper Setting](#reproducing-the-paper-setting)
- [Baselines](#baselines)
- [Analysis](#analysis)
- [Configuration Notes](#configuration-notes)
- [Dataset](#dataset)
- [Citation](#citation)
- [License](#license)

## Architecture Overview

HiGMem processes each conversation turn incrementally:

1. **Turn construction**: each raw dialogue turn is converted into a `TurnNote` with metadata.
2. **Event affiliation**: the new turn is assigned to existing events or starts a new event.
3. **Event update**: event metadata and summaries are updated as the conversation grows.
4. **Retrieval for QA**: the question is rewritten into retrieval keywords, candidate events and turns are retrieved, and an LLM filter selects final evidence turns.
5. **Final answer generation**: the final QA prompt uses the retrieved turns and follows the LoCoMo prompt family aligned with A-Mem.

## Repository Structure

```text
.
 data/
    locomo10.json              # LoCoMo-10 data used for reproduction
    README.md                  # Dataset note
 run_fphm_evaluation.py         # Main HiGMem evaluation script
 fphm_core.py                   # HiGMem memory construction and retrieval core
 memory_layer.py                # LLM and embedding backend utilities
 prompts.py                     # Prompt templates
 oracle_test.py                 # Oracle evidence baseline
 full_context_test.py           # Full-context baseline
 analyze_recall.py              # Single-run retrieval analysis
 analyze_recall_full.py         # Full-run retrieval analysis
 requirements.txt
 CITATION.bib
 LICENSE
```

## Installation

This codebase is tested with **Python 3.9**.

Create and activate a virtual environment:

```bash
python3.9 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install PyTorch first. Choose the wheel matching your CUDA version. Example for CUDA 12.4:

```bash
pip install torch==2.4.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

Then install the remaining dependencies:

```bash
pip install -r requirements.txt
```

Configure API credentials with environment variables or a local `.env` file:

```bash
OPENAI_API_KEY=sk-...
# Optional for OpenAI-compatible servers such as vLLM
OPENAI_API_BASE=http://127.0.0.1:8000/v1
```

## Quick Start

Run a single LoCoMo sample:

```bash
python run_fphm_evaluation.py --model gpt-4o-mini --backend openai --ablation-no-profile --ablation-event-metadata-only --ablation-no-link --k_event 10 --sample_index 0
```

The first run may download the sentence-transformer embedding model used for vector retrieval.

## Reproducing the Paper Setting

Use the following command for the main HiGMem LoCoMo setting:

```bash
python run_fphm_evaluation.py --model gpt-4o-mini --backend openai --ablation-no-profile --ablation-event-metadata-only --ablation-no-link --k_event 10 --num-workers 5
```

This configuration corresponds to:

- query rewriting enabled by default;
- character profiles disabled;
- event metadata mode enabled;
- immediate turn-turn links disabled;
- `k_event = 10`.

For an OpenAI-compatible local server, for example vLLM:

```bash
python run_fphm_evaluation.py --model Qwen2.5-7B-Instruct --backend openai --api_base http://127.0.0.1:8010/v1 --api_key EMPTY --ablation-no-profile --ablation-event-metadata-only --ablation-no-link --k_event 10 --num-workers 5
```

The code does not set an explicit `max_tokens` limit for OpenAI-compatible endpoints; context limits are controlled by the model server.

## Baselines

Oracle evidence baseline:

```bash
python oracle_test.py --model gpt-4o-mini --backend openai --num-workers 5
```

Full-context baseline:

```bash
python full_context_test.py --model gpt-4o-mini --backend openai --num-workers 5
```

## Analysis

Analyze the latest single-sample run:

```bash
python analyze_recall.py
```

Analyze the latest full-dataset run:

```bash
python analyze_recall_full.py
```

Generated outputs are written to:

- `fphm_runs/`: full-run logs, checkpoints, and aggregated results;
- `fphm_logs/`: single-sample logs;
- `checkpoints/`: single-sample memory checkpoints;
- `results/`: single-sample metrics;
- `analysis_results/`: recall, precision, and cost analysis tables.

These generated directories are ignored by Git.

## Configuration Notes

The main evaluation script exposes ablation flags used in our experiments:

- `--ablation-no-profile`
- `--ablation-event-title-only`
- `--ablation-event-metadata-only`
- `--ablation-attribute-profile`
- `--ablation-no-fact-judgment`
- `--ablation-no-filter`
- `--ablation-no-link`
- `--ablation-no-event`
- `--ablation-mpnet-retrieval`
- `--disable_query_rewriting_llm`

For the main paper setting, use:

```bash
--ablation-no-profile --ablation-event-metadata-only --ablation-no-link --k_event 10
```

## Dataset

For convenience, this repository includes `data/locomo10.json`, the LoCoMo-10 data split used by our reproduction scripts. LoCoMo is a public long-term conversation benchmark; please refer to the original LoCoMo release at [snap-research/locomo](https://github.com/snap-research/locomo) for dataset provenance and usage terms.

## Citation

If you use this code, please cite:

```bibtex
@inproceedings{cao2026higmem,
  title     = {HiGMem: A Hierarchical and LLM-Guided Memory System for Long-Term Conversational Agents},
  author    = {Cao, Shuqi and He, Jingyi and Tan, Fei},
  booktitle = {Findings of the Association for Computational Linguistics: ACL 2026},
  year      = {2026},
  publisher = {Association for Computational Linguistics},
  url       = {https://github.com/ZeroLoss-Lab/HiGMem}
}
```

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for details.
