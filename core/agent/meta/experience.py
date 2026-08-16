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
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

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
    """自愈经验库（JSONL 追加; 线程安全）。"""

    def __init__(self, path: str = "", max_entries: int = 500):
        self._path = path or _default_path()
        self._lock = threading.Lock()
        self._entries: List[Dict[str, Any]] = []
        self._max = max_entries
        self._load()

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
        with self._lock:
            self._entries.append(rec)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max:]
            self._persist(rec)
        return rec

    def _persist(self, rec: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("experience persist failed: %s", e)

    def search(self, text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """检索相似经验（诊断时作为 prior 证据注入, 贝叶斯先验）。"""
        q = (text or "").lower()
        if not q:
            return []
        scored = []
        with self._lock:
            for e in self._entries:
                hay = " ".join([
                    e.get("scope", ""), e.get("root_cause", ""),
                    e.get("fix_summary", ""), e.get("design_lesson", "")])
                score = sum(1 for w in q.split()[:8]
                            if w.lower() in hay)
                if score > 0:
                    scored.append((score, e))
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:limit]]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total": len(self._entries),
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
