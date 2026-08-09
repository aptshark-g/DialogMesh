# -*- coding: utf-8 -*-
"""孤儿组件 → 设计文档追溯（2026-08-08, 分批）。

用法: python scripts/_gap_trace_20260808.py <batch>
  batch: registry | recall | reliability | engineering | monitor
输出: data/_gap_trace_20260808.txt (UTF-8)
"""
import re
import sys
from pathlib import Path

BATCH = sys.argv[1] if len(sys.argv) > 1 else "registry"

# 组件名 → 检索关键词（类名 + 设计概念词）
BATCHES = {
    "registry": [
        ("granularity", ["granularity", "粒度调节", "granularity_regulator"]),
        ("causal_substrate", ["causal_substrate", "因果基板", "CausalSubstrate"]),
        ("belief_map", ["belief_map", "信念图", "belief map"]),
        ("context_ir_compiler", ["context_ir", "ContextIR", "跨域 IR", "cross_domain_ir"]),
        ("format_serializer", ["format_serializer", "序列化", "serializer"]),
        ("event_log_store", ["event_log_store", "事件日志存储", "EventLogStore"]),
        ("llm_coref_verifier", ["coref", "共指", "llm_coref"]),
        ("cascade_detector", ["cascade", "级联检测"]),
        ("nats_bridge", ["NATS", "nats"]),
        ("pg_bridge", ["pg_bridge", "Postgres", "postgres"]),
        ("redis_hotstore", ["redis", "Redis"]),
        ("otel_bridge", ["otel", "OpenTelemetry", "opentelemetry"]),
    ],
    "recall": [
        ("HybridSearchEngine", ["HyDE", "hybrid_hyde", "假设文档", "混合检索"]),
        ("WaveQueryEngine", ["WaveQuery", "水波", "wave_query", "多跳"]),
        ("LSHIndex", ["LSH", "lsh"]),
        ("SafeUnifiedSearch", ["SafeUnified", "store_safety", "统一搜索"]),
        ("TopicBacktracker", ["TopicBacktracker", "主题回溯", "discourse_gaps"]),
        ("FormatRouter", ["FormatRouter", "格式路由"]),
    ],
    "reliability": [
        ("AuditTrail", ["AuditTrail", "audit_trail", "审计轨迹", "A17"]),
        ("WriteAheadLog", ["WriteAheadLog", "write_ahead", "WAL", "预写日志", "崩溃恢复"]),
    ],
    "engineering": [
        ("PCRBridge", ["engineering_bridges", "PCRBridge", "工程链桥"]),
        ("IntentBridge", ["IntentBridge", "engineering_bridges"]),
        ("ContextManagerBridge", ["ContextManagerBridge"]),
        ("ServiceLayerBridge", ["ServiceLayerBridge"]),
        ("CognitiveProfileBridge", ["CognitiveProfileBridge"]),
        ("ObservabilityBridge", ["ObservabilityBridge"]),
        ("RegexExtractionProvider", ["ExtractionProvider", "extraction_blueprint", "提取蓝图"]),
        ("StanzaExtractionProvider", ["Stanza", "stanza"]),
        ("LMStudioExtractionProvider", ["LMStudio"]),
        ("DeepSeekExtractionProvider", ["DeepSeek"]),
        ("BehaviorAdapter", ["multi_domain", "多域适配", "BehaviorAdapter"]),
        ("UserProfileAdapter", ["UserProfileAdapter"]),
        ("CausalAdapter", ["CausalAdapter"]),
    ],
    "monitor": [
        ("EngineeringMonitor", ["EngineeringMonitor", "工程监控"]),
        ("SandboxExecutor", ["SandboxExecutor", "沙箱执行"]),
        ("MetaSelfRepair", ["MetaSelfRepair", "自修复"]),
        ("LearningLoop", ["LearningLoop", "学习循环"]),
        ("PersistenceManager", ["PersistenceManager", "持久化管理"]),
        ("MemoryManager", ["MemoryManager", "记忆管理"]),
        ("ProfileEvolution", ["ProfileEvolution", "画像演化"]),
        ("MoodClassifierLLM", ["MoodClassifier", "情绪分类"]),
        ("NATSBridge", ["NATS"]),
        ("ChromaBridge", ["Chroma", "chromadb"]),
        ("OTelBridge", ["otel", "OpenTelemetry"]),
    ],
}

DOCS = list(Path("docs").rglob("*.md"))
OUT = []


def log(*a):
    OUT.append(" ".join(str(x) for x in a))


def find_in_docs(terms):
    """返回 [(doc, line, snippet)]"""
    hits = []
    for d in DOCS:
        try:
            txt = d.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            low = line.lower()
            if any(t.lower() in low for t in terms):
                hits.append((d, i, line.strip()[:110]))
    return hits


log("=" * 70)
log(f"批次: {BATCH} | 设计文档 {len(DOCS)} 个")
for name, terms in BATCHES[BATCH]:
    hits = find_in_docs(terms)
    log("-" * 70)
    log(f"[{name}] 关键词 {terms}")
    if not hits:
        log("  ⚠️ 设计文档无直接引用（或名称不同）")
    for d, i, line in hits[:6]:
        log(f"    {str(d).replace(chr(92), '/')}:{i} {line}")

Path(f"data/_gap_trace_{BATCH}_20260808.txt").write_text("\n".join(OUT), encoding="utf-8")
print(f"done, lines: {len(OUT)}")
