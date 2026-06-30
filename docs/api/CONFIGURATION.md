# MemoryGraph Configuration Reference

> Complete table of all configurable parameters, their defaults, types, and descriptions.  
> Configuration is loaded in three layers (priority descending): **Environment Variables** → **User YAML** (`~/.config/memorygraph/discourse.yaml`) → **Code Defaults**.

---

## Environment Variable Syntax

Environment variables use the prefix `MEMORYGRAPH_` and double underscores (`__`) to denote nesting.

```bash
# Example: set segmenter threshold via env
MEMORYGRAPH_SEGMENTER__THRESHOLD=0.7

# Example: disable BDI
MEMORYGRAPH_SEGMENTER__BDI_ENABLED=false

# Example: reduce hot turns
MEMORYGRAPH_MANAGER__HOT_TURNS=3
```

---

## Configuration Table

### Encoder (`encoder`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `model_path` | `str` | `models/BAAI/bge-small-zh` | HuggingFace model ID or local path for the BGE semantic encoder. |
| `device` | `str` | `auto` | Compute device: `auto` (cuda if available), `cpu`, or `cuda`. |
| `cache_size` | `int` | `10000` | Maximum number of text embeddings kept in the LRU cache. |
| `max_length` | `int` | `512` | Token limit passed to the tokenizer. |

**Env examples:**
```bash
MEMORYGRAPH_ENCODER__MODEL_PATH=models/BAAI/bge-small-zh
MEMORYGRAPH_ENCODER__DEVICE=cpu
MEMORYGRAPH_ENCODER__MAX_LENGTH=256
```

---

### Parser (`parser`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ner_enabled` | `bool` | `true` | Enable DAMO NER pipeline (requires `addict`/`datasets`). Fallback to jieba+BGE if unavailable. |
| `bge_filter_enabled` | `bool` | `true` | Use BGE cosine similarity to filter low-confidence entity spans. |
| `bge_filter_threshold` | `float` | `0.5` | Minimum cosine similarity for an entity span to be retained. |

**Env examples:**
```bash
MEMORYGRAPH_PARSER__NER_ENABLED=false
MEMORYGRAPH_PARSER__BGE_FILTER_THRESHOLD=0.6
```

---

### Decomposer (`decomposer`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `complex_clause_length` | `int` | `30` | Character length above which a clause is considered complex if it contains no explicit entities. |
| `max_clauses_per_input` | `int` | `5` | If the input splits into more clauses than this, the hybrid path returns `parse_failed=True`. |
| `hybrid_path_enabled` | `bool` | `true` | Enable the "complex input" fallback path (return single failed clause instead of unreliable parse). |
| `semantic_parser_enabled` | `bool` | `true` | Use `SemanticParser` for entity and relation extraction. |

**Env examples:**
```bash
MEMORYGRAPH_DECOMPOSER__MAX_CLAUSES_PER_INPUT=8
MEMORYGRAPH_DECOMPOSER__HYBRID_PATH_ENABLED=false
```

---

### Header Injector (`injector`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `context_window_size` | `int` | `5` | Number of recent turns scanned for entity cache building. |
| `domain` | `str` | `default` | Domain key inside the knowledge base JSON/YAML. |
| `kb_path` | `Optional[str]` | `null` | Custom path to the header KB. Defaults to `~/.memorygraph/kb/header_kb.json`. |
| `semantic_parser_enabled` | `bool` | `true` | Use `SemanticParser` for entity extraction and coreference chains. |

**Env examples:**
```bash
MEMORYGRAPH_INJECTOR__CONTEXT_WINDOW_SIZE=3
MEMORYGRAPH_INJECTOR__DOMAIN=reverse_engineering
```

---

### Segmenter (`segmenter`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `threshold` | `float` | `0.5` | Fused cohesion threshold below which a boundary is created. Higher = stricter boundaries. |
| `macro_weight` | `float` | `0.6` | Weight of macro dimensions in the fused cohesion score. |
| `micro_weight` | `float` | `0.4` | Weight of micro dimensions in the fused cohesion score. |
| `bdi_enabled` | `bool` | `true` | Enable Burst Drift of Intent detection (intent-label mismatch → forced boundary). |

**Env examples:**
```bash
MEMORYGRAPH_SEGMENTER__THRESHOLD=0.65
MEMORYGRAPH_SEGMENTER__BDI_ENABLED=false
MEMORYGRAPH_SEGMENTER__MACRO_WEIGHT=0.7
```

---

### Manager (`manager`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `hot_turns` | `int` | `5` | Turn distance ≤ this value → `ACTIVE` (hot) state. |
| `cooling_turns` | `int` | `5` | Turns in `(hot_turns, hot_turns + cooling_turns]` → `COOLING` (warm) state. |
| `cold_turns` | `int` | `10` | Turns > `hot_turns + cooling_turns` → `COLD` state. |
| `merge_threshold` | `float` | `0.55` | Inter-block cohesion ≥ this value → merge new block into active block. |

**Env examples:**
```bash
MEMORYGRAPH_MANAGER__HOT_TURNS=3
MEMORYGRAPH_MANAGER__COOLING_TURNS=7
MEMORYGRAPH_MANAGER__MERGE_THRESHOLD=0.6
```

---

### Summary Engine (`summary`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `v3_trigger_turn_count` | `int` | `5` | Minimum number of turns inside a block before the v3 evolutionary summary is generated. |

**Env examples:**
```bash
MEMORYGRAPH_SUMMARY__V3_TRIGGER_TURN_COUNT=10
```

---

### Context Builder (`context`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `hot_turns` | `int` | `5` | Same as manager hot_turns; determines which blocks receive full text vs. summary. |

**Env examples:**
```bash
MEMORYGRAPH_CONTEXT__HOT_TURNS=5
```

---

### Pipeline (`pipeline`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | `bool` | `true` | Master on/off switch for the entire DiscourseBlockTree pipeline. When `false`, `process_turn()` returns `""`. |
| `hot_turns` | `int` | `5` | Default hot_turns passed to Manager and ContextBuilder if not overridden. |

**Env examples:**
```bash
MEMORYGRAPH_PIPELINE__ENABLED=false
MEMORYGRAPH_PIPELINE__HOT_TURNS=4
```

---

### Model Download (`model_download`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `bge_model_id` | `str` | `BAAI/bge-small-zh` | HuggingFace model ID for the BGE encoder. |
| `ner_model_id` | `str` | `damo/nlp_raner_named-entity-recognition_chinese-base-news` | ModelScope model ID for the Chinese NER model. |
| `cache_dir` | `str` | `models` | Local directory where models are downloaded and cached. |

**Env examples:**
```bash
MEMORYGRAPH_MODEL_DOWNLOAD__CACHE_DIR=/mnt/models
```

---

### Logging (`logging`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `level` | `str` | `INFO` | Python logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `format` | `str` | `%(asctime)s - %(name)s - %(levelname)s - %(message)s` | Plain-text log format string. |
| `json` | `bool` | `false` | When `true`, output structured JSON logs suitable for log collectors (e.g., ELK, Loki). |

**Env examples:**
```bash
MEMORYGRAPH_LOGGING__LEVEL=DEBUG
MEMORYGRAPH_LOGGING__JSON=true
```

---

## YAML Config File Template

Save this as `~/.config/memorygraph/discourse.yaml`:

```yaml
# Discourse Block Tree 配置文件
# 优先级：环境变量 > 本文件 > 代码默认值

encoder:
  model_path: models/BAAI/bge-small-zh
  device: auto
  cache_size: 10000
  max_length: 512

parser:
  ner_enabled: true
  bge_filter_enabled: true
  bge_filter_threshold: 0.5

decomposer:
  complex_clause_length: 30
  max_clauses_per_input: 5
  hybrid_path_enabled: true
  semantic_parser_enabled: true

injector:
  context_window_size: 5
  domain: default
  kb_path: null
  semantic_parser_enabled: true

segmenter:
  threshold: 0.5
  macro_weight: 0.6
  micro_weight: 0.4
  bdi_enabled: true

manager:
  hot_turns: 5
  cooling_turns: 5
  cold_turns: 10
  merge_threshold: 0.55

summary:
  v3_trigger_turn_count: 5

context:
  hot_turns: 5

pipeline:
  enabled: true
  hot_turns: 5

model_download:
  bge_model_id: BAAI/bge-small-zh
  ner_model_id: damo/nlp_raner_named-entity-recognition_chinese-base-news
  cache_dir: models

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  json: false
```

---

## Runtime Reconfiguration

The configuration is loaded lazily on first `get_discourse_config()` call. To reload at runtime (e.g., after editing the YAML file):

```python
from core.agent.config.discourse_config import reload_discourse_config

config = reload_discourse_config()
print(config.segmenter.threshold)  # new value
```

**Note:** Components that cache config values at construction time (e.g., `Segmenter`, `Manager`) will **not** automatically pick up the new values. You must reinstantiate them or call their own reload methods if provided.

---

## Type Coercion Rules (Environment Variables)

All environment variable values are strings. The loader applies the following coercion:

| String value | Coerced type | Examples |
|--------------|--------------|----------|
| `true`, `1`, `yes`, `on` | `bool` `True` | `MEMORYGRAPH_PIPELINE__ENABLED=true` |
| `false`, `0`, `no`, `off` | `bool` `False` | `MEMORYGRAPH_SEGMENTER__BDI_ENABLED=false` |
| Contains `.` | `float` | `MEMORYGRAPH_SEGMENTER__THRESHOLD=0.7` |
| Integer parseable | `int` | `MEMORYGRAPH_MANAGER__HOT_TURNS=3` |
| Everything else | `str` | `MEMORYGRAPH_ENCODER__DEVICE=cpu` |

---

## Plugin Strategy Overrides

In addition to YAML/env config, the `DiscoursePipeline` accepts a `strategy` dict for custom component injection via the plugin registry:

```python
from core.agent.discourse_integration import DiscoursePipeline
from core.agent.plugin_system import PluginRegistry

PluginRegistry.register_strategy(
    name="strict_segmenter",
    component_type="segmenter",
    factory_func=lambda: StrictSegmenter(threshold=0.8),
)

dp = DiscoursePipeline(strategy={"segmenter": "strict_segmenter"})
```

This is **independent** of the YAML/env configuration and takes precedence at instantiation time.
