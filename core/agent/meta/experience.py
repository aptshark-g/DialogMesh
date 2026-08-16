# -*- coding: utf-8 -*-
"""自愈经验库（贝叶斯 prior 累积, 2026-08-16）。

设计: SELF_REPAIR_DESIGN_20260816 §八 + PARADIGM A13（长证明后验）+
伪二阶抽象（逆推验证的凝练）。

外部多 agent 修复无演进 = 缺"被修对象的设计约束"作先验（bc 在自己
约束上下文执行, 没有 a 的视角）。元认知持有 a 的约束 → 修复历史按
伪二阶抽象凝练为"可逆推的设计教训" → 写入经验库 → 后续诊断检索作为
prior 证据注入（贝叶斯式累积）。

2026-08-16 P1-③: design_lesson 凝练支持 LLM（DM_DIAG_LLM_LESSON=1 开启,
默认模板）——伪二阶抽象: 从"scope 失败 + 修复 + 设计约束"凝练可逆推的
教训, 而非固定句式。

2026-08-16 P2-①: 经验检索升级 RAG —— 条目写入时向量化（BGE-M3, 1024 维,
sidecar 持久化 `self_repairs.vectors.json`）; 检索 = 语义余弦 + 关键词加权
（DM_EXPERIENCE_RAG=0 可关; BGE 不可用自动降级关键词）。语义检索让"网关
连不上"能命中"connection refused 工具失败"这类无关键词重合的既往经验。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


GATEWAY_URL = "http://127.0.0.1:8080/v1/chat/completions"
LESSON_PROMPT_TEMPLATE = (
    "你是 DialogMesh 元认知凝练器。基于一次修复（scope/根因/修复方式/设计约束）, "
    "凝练一条**可逆推的设计教训**（伪二阶抽象: 教训须能反推回失败场景与修复意图, "
    "不是泛泛而谈）。输出 JSON（不要其他文字）:\n"
    "{{\"design_lesson\": \"≤120字, 中文, 含'复用时先核对…'的可操作指引\"}}\n\n"
    "scope: {scope}\n根因: {root_cause}\n修复: {fix_summary}\n"
    "设计约束: {design}"
)


def _default_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))),
        "data", "self_repairs.jsonl")


class ExperienceStore:
    """自愈经验库（JSONL 追加 + 向量 sidecar; 线程安全）。

    RAG（2026-08-16 P2-①）: add 时经 vectorizer 编码 → sidecar 持久化;
    search = 语义余弦 + 关键词加权, 排序后取 top-k。向量与条目按 ts 对齐
    （JSONL 追加, ts 单调）。vectorizer 可注入（测试/离线）, 默认
    SemanticEncoder（BGE-M3）。编码失败/禁用 → 关键词检索兜底。
    """

    def __init__(self, path: str = "", max_entries: int = 500,
                 vectorizer: Any = None, rag_enabled: Optional[bool] = None):
        self._path = path or _default_path()
        self._lock = threading.Lock()
        self._entries: List[Dict[str, Any]] = []
        self._vectors: List[Optional[np.ndarray]] = []
        self._max = max_entries
        self._vectorizer = vectorizer
        self._rag_enabled = self._resolve_rag(rag_enabled)
        self._load()

    @staticmethod
    def _resolve_rag(rag_enabled: Optional[bool]) -> bool:
        if rag_enabled is not None:
            return bool(rag_enabled)
        return os.environ.get("DM_EXPERIENCE_RAG", "1").lower() not in (
            "0", "false", "off", "no")

    def _vector_path(self) -> str:
        return os.path.splitext(self._path)[0] + ".vectors.json"

    @staticmethod
    def _entry_text(e: Dict[str, Any]) -> str:
        return " ".join([
            str(e.get("scope", "")), str(e.get("root_cause", "")),
            str(e.get("fix_summary", "")), str(e.get("design_lesson", ""))])

    def _vectorize(self, texts: List[str]) -> Optional[np.ndarray]:
        """编码文本; 不可用/失败 → None（走关键词兜底）。"""
        if not self._rag_enabled or not texts:
            return None
        vec = self._vectorizer
        if vec is None:
            try:
                from core.agent.compiler.semantic_encoder import (
                    _global_encoder, get_encoder)
                # 不触发冷加载: 模型未就绪（未预热/测试环境）→ 关键词兜底。
                # 生产由启动预热（prewarm_models）保证就绪。
                if _global_encoder is None or not _global_encoder._initialized:
                    return None
                vec = get_encoder()
            except Exception:
                vec = None
        if vec is None or not hasattr(vec, "encode"):
            return None
        try:
            arr = np.asarray(vec.encode(texts), dtype=np.float64)
            return arr
        except Exception as e:
            logger.debug("experience vectorize failed: %s", e)
            return None

    def _load(self) -> None:
        try:
            if not os.path.exists(self._path):
                return
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f.readlines()[-self._max:]:
                    line = line.strip()
                    if line:
                        try:
                            self._entries.append(json.loads(line))
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("experience load failed: %s", e)
        finally:
            self._load_vectors()

    def _load_vectors(self) -> None:
        """sidecar 按 ts 对齐; 缺失向量惰性补算（重算不丢语义检索）。"""
        self._vectors = [None] * len(self._entries)
        try:
            vp = self._vector_path()
            if os.path.exists(vp):
                with open(vp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                by_ts = {}
                for d in data:
                    vec = d.get("vec")
                    if vec:
                        by_ts[float(d.get("ts", 0))] = np.asarray(
                            vec, dtype=np.float64)
                for i, e in enumerate(self._entries):
                    self._vectors[i] = by_ts.get(float(e.get("ts", 0)))
        except Exception as e:
            logger.debug("experience vectors load failed: %s", e)
        # 惰性补算缺失向量（如 sidecar 重建/条目被 trim 后重新对齐）
        missing = [i for i, v in enumerate(self._vectors) if v is None]
        if missing:
            arr = self._vectorize(
                [self._entry_text(self._entries[i]) for i in missing])
            if arr is not None:
                for j, i in enumerate(missing):
                    self._vectors[i] = arr[j]
                self._persist_vectors()

    def add(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """追加经验条目（根因/修复/设计教训/影响公理）。"""
        rec = {
            "ts": time.time(),
            "scope": str(entry.get("scope", "")),
            "root_cause": str(entry.get("root_cause", ""))[:300],
            "fix_summary": str(entry.get("fix_summary", ""))[:300],
            "design_lesson": str(entry.get("design_lesson", ""))[:500],
            "axioms": list(entry.get("axioms", [])),
            "verify_passed": bool(entry.get("verify_passed", True)),
            "source": str(entry.get("source", "diagnosis")),
        }
        vec = None
        if self._rag_enabled:
            arr = self._vectorize([self._entry_text(rec)])
            if arr is not None:
                vec = arr[0]
        with self._lock:
            self._entries.append(rec)
            self._vectors.append(vec)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max:]
                self._vectors = self._vectors[-self._max:]
            self._persist(rec)
        if self._rag_enabled and vec is not None:
            self._persist_vectors()
        return rec

    def _persist(self, rec: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("experience persist failed: %s", e)

    def _persist_vectors(self) -> None:
        """sidecar 全量落盘（条目 ≤500, 体积小; 简单可靠）。"""
        try:
            with self._lock:
                data = []
                for e, v in zip(self._entries, self._vectors):
                    if v is not None:
                        data.append({
                            "ts": e.get("ts", 0),
                            "vec": np.asarray(v, dtype=np.float64).tolist(),
                        })
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            tmp = self._vector_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self._vector_path())
        except Exception as e:
            logger.debug("experience vectors persist failed: %s", e)

    def search(self, text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """检索相似经验（语义 + 关键词混合; 诊断时作为 prior 证据注入）。"""
        q = (text or "").lower()
        if not q:
            return []
        qvec = None
        if self._rag_enabled:
            arr = self._vectorize([text])
            if arr is not None:
                qvec = arr[0]
        scored = []
        with self._lock:
            for i, e in enumerate(self._entries):
                hay = self._entry_text(e).lower()
                score = sum(1 for w in q.split()[:8]
                            if w in hay)
                sim = 0.0
                if qvec is not None and self._vectors[i] is not None:
                    sim = float(np.dot(self._vectors[i], qvec))
                if qvec is not None and self._vectors[i] is not None:
                    if sim < 0.15 and score == 0:
                        continue  # 语义噪声过滤（无关键词重合且不相似）
                    total = sim + 0.15 * score
                else:
                    if score == 0:
                        continue
                    total = float(score)
                scored.append((total, e))
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:limit]]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            vectorized = sum(1 for v in self._vectors if v is not None)
            return {
                "total": len(self._entries),
                "rag": {
                    "enabled": self._rag_enabled,
                    "vectorized": vectorized,
                    "backend": (
                        "semantic" if self._rag_enabled and vectorized > 0
                        else ("semantic_pending" if self._rag_enabled
                              else "keyword")),
                },
                "recent": list(self._entries[-10:]),
            }


_store: Optional[ExperienceStore] = None


def get_experience_store(path: str = "") -> ExperienceStore:
    global _store
    if _store is None:
        _store = ExperienceStore(path=path)
    return _store


def record_experience(entry: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return get_experience_store().add(entry)
    except Exception:
        return {}


def search_experience(text: str, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        return get_experience_store().search(text, limit=limit)
    except Exception:
        return []


def _template_lesson(scope: str, root_cause: str,
                     fix_summary: str) -> str:
    """默认模板凝练（无 LLM / 开关关）——可逆推句式。"""
    return (
        "scope %s 曾失败并修复: %s — 复用时先核对该 scope 的设计约束与测试, "
        "修复须可逆推回设计意图。" % (scope, (root_cause or fix_summary)[:120]))


def _llm_lesson(scope: str, root_cause: str, fix_summary: str,
                design: str, gateway_url: str = GATEWAY_URL) -> str:
    """LLM 凝练（DM_DIAG_LLM_LESSON=1 时）; 失败/超时 → 空串（走模板）。"""
    prompt = LESSON_PROMPT_TEMPLATE.format(
        scope=scope, root_cause=(root_cause or "")[:200],
        fix_summary=(fix_summary or "")[:200],
        design=(design or "")[:800])
    try:
        import urllib.request
        body = json.dumps({
            "provider": "deepseek", "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "disabled"},
            "max_tokens": 300, "temperature": 0.1,
        }).encode("utf-8")
        req = urllib.request.Request(
            gateway_url, data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer dm-client"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            d = json.loads(resp.read())
        text = (d["choices"][0]["message"].get("content") or "").strip()
        t = text.strip()
        if t.startswith("```"):
            t = t.strip("`")
            if t.startswith("json"):
                t = t[4:]
            t = t.strip()
        start = t.find("{")
        end = t.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(t[start:end + 1])
            lesson = str(data.get("design_lesson", "")).strip()
            if lesson:
                return lesson[:300]
    except Exception as e:
        logger.debug("llm lesson failed: %s", e)
    return ""


def condense_lesson(scope: str, root_cause: str, fix_summary: str,
                    design: str = "") -> str:
    """凝练 design_lesson: LLM（开关开, 失败降级）→ 模板兜底。"""
    if os.environ.get("DM_DIAG_LLM_LESSON", "").lower() in (
            "1", "true", "on", "yes"):
        lesson = _llm_lesson(scope, root_cause, fix_summary, design)
        if lesson:
            return lesson
    return _template_lesson(scope, root_cause, fix_summary)
