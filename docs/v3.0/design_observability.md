# 可观测性（Observability）设计方案 v1.0

> 本文档定义意图识别引擎的可观测性架构，包括结构化日志、实时指标聚合、质量告警和文本仪表盘。解决当前"黑盒运行、无法量化质量"的问题。

## 目录

- [1. 背景与问题](#1-背景与问题)
- [2. 设计目标](#2-设计目标)
- [3. 核心设计：三层观测架构](#3-核心设计三层观测架构)
- [4. 关键组件](#4-关键组件)
- [5. 日志规范](#5-日志规范)
- [6. 指标与告警](#6-指标与告警)
- [7. 仪表盘设计](#7-仪表盘设计)
- [8. 与 CLI 集成方案](#8-与-cli-集成方案)
- [9. 测试策略](#9-测试策略)
- [10. 实现计划](#10-实现计划)
- [11. 风险与回退](#11-风险与回退)

---

## 1. 背景与问题

### 当前状态

```python
# 当前 CLI 输出 — 纯文本，无法分析
print(f"  执行状态: {exec_result.status}")
print(f"  LLM 调用次数: {llm_call_count} 次")
```

### 问题

| 问题 | 影响 | 触发场景 |
|---|---|---|
| 无结构化日志 | 无法事后分析 "为什么这次解析错了" | 任何异常场景 |
| 无质量指标 | 不知道澄清率是否在恶化 | 长期运行 |
| 无性能监控 | 不知道延迟瓶颈在哪 | 用户抱怨卡顿 |
| 无告警机制 | 系统降级时无感知 | 规则覆盖率下降 |
| 无法对比实验 | A/B 测试无法量化效果 | 优化策略时 |

### 工业级对比

| 能力 | 工业级标准（如 Datadog） | 当前状态 |
|---|---|---|
| 结构化日志 | JSON/Protobuf 每轮输出 | ❌ 纯文本 print |
| 指标聚合 | 实时计数器 + 直方图 | ❌ 无 |
| 分布式追踪 | trace_id 跨服务传递 | ❌ 无 |
| 告警 | 阈值触发 + 通知 | ❌ 无 |
| 仪表盘 | 实时可视化 | ❌ 无 |

---

## 2. 设计目标

### 功能目标

| ID | 目标 | 优先级 | 验收标准 |
|---|---|---|---|
| OB-1 | 每轮决策链结构化日志 | P0 | 每轮输出一行 JSON，可机器解析 |
| OB-2 | 实时会话质量指标 | P0 | 澄清率、置信度、LLM 回退率实时计算 |
| OB-3 | 质量告警（自动触发） | P0 | 澄清率 >30% 时打印告警 |
| OB-4 | 文本仪表盘（实时） | P1 | CLI 中 `stats` 指令显示实时指标 |
| OB-5 | 日志持久化到文件 | P1 | 按天切分，JSONL 格式 |
| OB-6 | 会话级报告（结束时输出） | P2 | 会话关闭时打印完整质量报告 |
| OB-7 | 多会话对比 | P2 | 支持跨会话 A/B 对比（规则 vs LLM 策略） |

### 非功能目标

| ID | 目标 | 指标 |
|---|---|---|
| N-1 | 日志写入延迟 | 单次日志 < 1ms（异步写入） |
| N-2 | 内存占用 | 指标聚合器 < 10MB（滑动窗口限制） |
| N-3 | 日志保留 | 默认 30 天，可配置 |
| N-4 | 无外部依赖 | 不依赖第三方日志服务（如 ELK） |
| N-5 | 可禁用 | 通过 `--no-observability` 完全关闭观测 |

---

## 3. 核心设计：三层观测架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: 仪表盘/CLI 展示 (Dashboard)                            │
│  ─────────────────────────────────────────────────────────────  │
│  实时输出：                                                      │
│  ┌────────────────────────────────────┐                          │
│  │ 📊 会话健康度: 78/100              │                          │
│  │ 总轮数: 25 | 澄清率: 12% | LLM回退: 8% │                      │
│  │ 平均置信度: 0.72 | 平均延迟: 45ms   │                          │
│  │ 意图分布: TOOL(18) ADVISOR(5) COMPANION(2) │                 │
│  │ ⚠️  告警: 无                        │                          │
│  └────────────────────────────────────┘                          │
│  CLI 指令: `stats` 显示当前会话指标                              │
│            `global` 显示全局统计                                  │
│            `alerts` 显示活跃告警                                  │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: 指标聚合 (MetricsAggregator)                           │
│  ─────────────────────────────────────────────────────────────  │
│  实时计算：                                                      │
│  • SessionMetrics（单会话）— 计数器 + 滑动窗口                    │
│  • GlobalMetrics（全局）— 最近 100 个会话聚合                      │
│  • AlertEngine（告警引擎）— 阈值检查 + 触发                       │
│  内存结构：                                                       │
│  current_sessions: Dict[str, SessionMetrics]                     │
│  window: Deque[SessionMetrics]  (maxlen=100)                       │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: 结构化日志 (StructuredLogger)                          │
│  ─────────────────────────────────────────────────────────────  │
│  每轮输出：                                                       │
│  {"timestamp": "2026-06-26T14:30:00", "session_id": "abc",       │
│   "query": "scan 100", "decision_chain": {...},                  │
│   "performance": {"total_latency_ms": 45, "llm_used": false},   │
│   "quality_signals": {"required_clarification": false, ...}}    │
│  输出路径：~/.memorygraph/logs/decisions_20260626.jsonl          │
│  写入模式：追加（append），按天切分                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 关键组件

### 4.1 StructuredLogger（结构化日志）

```python
# core/agent/observability/logger.py
import json
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class DecisionLogEntry:
    """单轮决策链日志条目。"""
    timestamp: str              # ISO-8601
    session_id: str
    query: str                  # 截断到 200 字符
    
    # 决策链
    pcr_expectation: Optional[str]
    pcr_noise: Optional[float]
    pcr_complexity: Optional[float]
    intent_category: Optional[str]
    intent_confidence: Optional[float]
    execution_status: Optional[str]
    strategy_action: Optional[str]  # ask_user / direct_reply / execute / None
    
    # 性能
    total_latency_ms: float
    llm_used: bool
    llm_latency_ms: float
    
    # 质量信号
    required_clarification: bool
    confidence_below_threshold: bool
    llm_fallback_triggered: bool
    
    # 窗口统计（如果启用了窗口管理）
    window_total_turns: Optional[int] = None
    window_compressed: Optional[bool] = None
    window_token_cost: Optional[int] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


class StructuredLogger:
    """
    结构化决策链日志器。
    每轮输出一行 JSON，便于后续分析和仪表盘消费。
    """
    
    DEFAULT_LOG_DIR = "~/.memorygraph/logs"
    
    def __init__(self, 
                 log_dir: str = None,
                 enable_console: bool = False,  # 是否同时输出到控制台
                 max_file_size_mb: int = 100,
                 enable_gzip: bool = True,      # 轮转后是否 gzip 压缩旧日志
                 retain_days: int = 30):         # 日志保留天数（自动清理过期文件）
        self.log_dir = Path(log_dir or self.DEFAULT_LOG_DIR).expanduser()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.enable_console = enable_console
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.enable_gzip = enable_gzip
        self.retain_days = retain_days
        
        # 按天切分文件
        self._current_date = None
        self._current_file = None
        self._current_size = 0
        
        self._ensure_file()
    
    def _ensure_file(self):
        """确保当前日期的日志文件已打开。"""
        date_str = datetime.now().strftime("%Y%m%d")
        if date_str != self._current_date or self._current_file is None:
            if self._current_file:
                self._current_file.close()
            
            self._current_date = date_str
            filepath = self.log_dir / f"decisions_{date_str}.jsonl"
            self._current_file = open(filepath, "a", encoding="utf-8")
            self._current_size = filepath.stat().st_size if filepath.exists() else 0
    
    def log(self, entry: DecisionLogEntry):
        """写入单条日志。"""
        self._ensure_file()
        
        line = json.dumps(entry.to_dict(), ensure_ascii=False, default=str) + "\n"
        self._current_file.write(line)
        self._current_file.flush()  # 确保落盘
        self._current_size += len(line.encode("utf-8"))
        
        # 控制台输出（可选）
        if self.enable_console:
            print(f"[LOG] {line.strip()}")
        
        # 文件大小检查（超过阈值时创建新文件）
        if self._current_size > self.max_file_size:
            self._rotate_file()
    
    def _rotate_file(self):
        """日志轮转：创建带时间戳的新文件，旧文件可选 gzip 压缩。"""
        if self._current_file:
            self._current_file.close()
        
        # 对旧文件进行 gzip 压缩（异步后台线程，不阻塞主流程）
        old_filepath = self.log_dir / f"decisions_{self._current_date}.jsonl"
        if self.enable_gzip and old_filepath.exists() and old_filepath.stat().st_size > 1024:
            self._gzip_async(old_filepath)
        
        timestamp = datetime.now().strftime("%H%M%S")
        new_name = f"decisions_{self._current_date}_{timestamp}.jsonl"
        self._current_file = open(self.log_dir / new_name, "a", encoding="utf-8")
        self._current_size = 0
    
    def _gzip_async(self, filepath: Path):
        """后台线程 gzip 压缩旧日志文件（不阻塞主流程）。"""
        import gzip
        import threading
        def _compress():
            gz_path = filepath.with_suffix(".jsonl.gz")
            with open(filepath, "rb") as f_in:
                with gzip.open(gz_path, "wb") as f_out:
                    f_out.write(f_in.read())
            filepath.unlink()  # 删除原始文件
        threading.Thread(target=_compress, daemon=True).start()
    
    def cleanup_old_logs(self, retain_days: int = None):
        """清理超过保留期的日志文件（包括 .jsonl 和 .jsonl.gz）。"""
        retain = retain_days or self.retain_days
        cutoff = datetime.now().timestamp() - (retain * 86400)
        for f in self.log_dir.iterdir():
            if f.name.startswith("decisions_") and f.suffix in (".jsonl", ".gz"):
                if f.stat().st_mtime < cutoff:
                    f.unlink()
    
    def log_turn(self,
                 session_id: str,
                 query: str,
                 pcr_output: Any,
                 parse_result: Any,
                 execution_status: str,
                 strategy_action: Optional[Dict],
                 total_latency_ms: float,
                 llm_used: bool,
                 llm_latency_ms: float = 0,
                 window_stats: Optional[Dict] = None):
        """便捷方法：从业务对象构建日志条目。"""
        entry = DecisionLogEntry(
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            query=query[:200],
            pcr_expectation=getattr(pcr_output, "expectation", None) if pcr_output else None,
            pcr_noise=getattr(pcr_output, "noise_level", None) if pcr_output else None,
            pcr_complexity=getattr(pcr_output, "complexity_level", None) if pcr_output else None,
            intent_category=str(getattr(parse_result.intent, "category", None)) if parse_result else None,
            intent_confidence=getattr(parse_result.intent, "confidence", None) if parse_result else None,
            execution_status=execution_status,
            strategy_action=strategy_action.get("action") if strategy_action else None,
            total_latency_ms=total_latency_ms,
            llm_used=llm_used,
            llm_latency_ms=llm_latency_ms,
            required_clarification=execution_status == "clarifying",
            confidence_below_threshold=(getattr(parse_result.intent, "confidence", 1.0) < 0.5) if parse_result else False,
            llm_fallback_triggered=strategy_action is not None,
            window_total_turns=window_stats.get("total_turns") if window_stats else None,
            window_compressed=window_stats.get("compressed") if window_stats else None,
            window_token_cost=window_stats.get("estimated_tokens") if window_stats else None,
        )
        self.log(entry)
    
    def close(self):
        """关闭日志文件。"""
        if self._current_file:
            self._current_file.close()
            self._current_file = None
```

### 4.2 SessionMetrics（单会话指标）

```python
# core/agent/observability/metrics.py
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List
import math


@dataclass
class SessionMetrics:
    """单会话实时指标。"""
    
    session_id: str
    start_time: float = field(default_factory=time.time)
    
    # 计数器
    total_turns: int = 0
    clarifications: int = 0
    llm_calls: int = 0
    rule_hits: int = 0          # 规则命中，未触发 LLM
    direct_replies: int = 0      # LLM 直接回复（短路）
    ask_user_count: int = 0      # 追问次数
    errors: int = 0
    
    # 累积值（用于计算平均）
    _confidence_sum: float = 0.0
    _latency_sum: float = 0.0
    _llm_latency_sum: float = 0.0
    
    # 分布（用于直方图）
    confidence_history: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    latency_history: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    
    # 意图分布
    intent_distribution: Counter = field(default_factory=Counter)
    
    # 状态机
    current_state: str = "active"  # active | idle | clarifying | closed
    fsm_external_state: str = "idle"  # 外部状态（idle | processing | clarifying | error | closed）
    
    def record_turn(self,
                    confidence: float,
                    total_latency_ms: float,
                    llm_used: bool,
                    llm_latency_ms: float = 0,
                    required_clarification: bool = False,
                    intent_category: str = "UNKNOWN",
                    execution_status: str = "ok"):
        """记录一轮对话的指标（意图分布只保留 top-5，其余归入 OTHER，防止 Counter 膨胀）。"""
        self.total_turns += 1
        self._confidence_sum += confidence
        self._latency_sum += total_latency_ms
        self.confidence_history.append(confidence)
        self.latency_history.append(total_latency_ms)
        self.intent_distribution[intent_category] += 1
        
        # 意图分布：只保留 top-5 高频意图，其余归入 OTHER，防止 Counter 膨胀
        if len(self.intent_distribution) > 5:
            all_items = self.intent_distribution.most_common()
            top_5 = set(intent for intent, _ in all_items[:5])
            for intent, count in all_items[5:]:
                if intent != "OTHER":
                    self.intent_distribution["OTHER"] += count
                    del self.intent_distribution[intent]
        
        if llm_used:
            self.llm_calls += 1
            self._llm_latency_sum += llm_latency_ms
        else:
            self.rule_hits += 1
        
        if required_clarification:
            self.clarifications += 1
        
        if execution_status == "direct_reply":
            self.direct_replies += 1
        elif execution_status == "clarifying":
            self.ask_user_count += 1
        elif execution_status == "error":
            self.errors += 1
    
    @property
    def avg_confidence(self) -> float:
        return self._confidence_sum / self.total_turns if self.total_turns > 0 else 0.0
    
    @property
    def avg_latency_ms(self) -> float:
        return self._latency_sum / self.total_turns if self.total_turns > 0 else 0.0
    
    @property
    def avg_llm_latency_ms(self) -> float:
        return self._llm_latency_sum / self.llm_calls if self.llm_calls > 0 else 0.0
    
    @property
    def clarification_rate(self) -> float:
        return self.clarifications / self.total_turns if self.total_turns > 0 else 0.0
    
    @property
    def llm_fallback_rate(self) -> float:
        return self.llm_calls / self.total_turns if self.total_turns > 0 else 0.0
    
    @property
    def rule_hit_rate(self) -> float:
        return self.rule_hits / self.total_turns if self.total_turns > 0 else 0.0
    
    @property
    def latency_p95(self) -> float:
        """95 分位延迟。"""
        if not self.latency_history:
            return 0.0
        sorted_lat = sorted(self.latency_history)
        idx = int(len(sorted_lat) * 0.95)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]
    
    @property
    def health_score(self) -> float:
        """
        会话健康度：0-100。
        
        计算公式：
        - 基础分: 100
        - 澄清率扣分: 每 1% 扣 0.5 分
        - 低置信度扣分: 平均置信度 < 0.5 时，每低 0.1 扣 5 分
        - LLM 回退率扣分: 每 1% 扣 0.2 分
        - 错误率扣分: 每 1% 扣 1.0 分
        """
        score = 100.0
        score -= self.clarification_rate * 50
        score -= max(0, (0.5 - self.avg_confidence)) * 50
        score -= self.llm_fallback_rate * 20
        score -= (self.errors / self.total_turns) * 100 if self.total_turns > 0 else 0
        return max(0, min(100, score))
    
    def to_dict(self) -> Dict:
        """导出为字典（用于仪表盘展示）。"""
        return {
            "session_id": self.session_id,
            "total_turns": self.total_turns,
            "clarification_rate": f"{self.clarification_rate*100:.1f}%",
            "llm_fallback_rate": f"{self.llm_fallback_rate*100:.1f}%",
            "rule_hit_rate": f"{self.rule_hit_rate*100:.1f}%",
            "avg_confidence": f"{self.avg_confidence:.2f}",
            "avg_latency_ms": f"{self.avg_latency_ms:.0f}ms",
            "latency_p95": f"{self.latency_p95:.0f}ms",
            "health_score": f"{self.health_score:.0f}/100",
            "intent_distribution": dict(self.intent_distribution.most_common(5)),
            "current_state": self.current_state,
            "fsm_external_state": self.fsm_external_state,
        }
```

### 4.3 MetricsAggregator（全局指标聚合）

```python
class MetricsAggregator:
    """
    全局指标聚合器。
    维护最近 N 个会话的滑动窗口统计。
    告警阈值从 ~/.memorygraph/config.json 读取，支持运行时热更新。
    """
    
    DEFAULT_WINDOW_SIZE = 100
    
    def __init__(self, window_size: int = None):
        self.window_size = window_size or self.DEFAULT_WINDOW_SIZE
        self.window: Deque[SessionMetrics] = deque(maxlen=self.window_size)
        self.current_sessions: Dict[str, SessionMetrics] = {}
        self._config = self._load_config()
    
    def _load_config(self) -> Dict:
        """加载告警配置（支持热更新）"""
        config_path = Path("~/.memorygraph/config.json").expanduser()
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("alerts", {})
            except (json.JSONDecodeError, OSError):
                pass
        return {}
    
    def _get_threshold(self, key: str, default: float) -> float:
        """获取全局告警阈值（优先从配置文件读取）"""
        return self._config.get("global", {}).get(key, default)
    
    def start_session(self, session_id: str) -> SessionMetrics:
        """开始新会话。"""
        metrics = SessionMetrics(session_id=session_id)
        self.current_sessions[session_id] = metrics
        return metrics
    
    def get_session(self, session_id: str) -> Optional[SessionMetrics]:
        """获取当前会话指标。"""
        return self.current_sessions.get(session_id)
    
    def record_turn(self, session_id: str, **kwargs):
        """记录一轮对话。"""
        if session_id not in self.current_sessions:
            self.start_session(session_id)
        self.current_sessions[session_id].record_turn(**kwargs)
    
    def end_session(self, session_id: str) -> Optional[SessionMetrics]:
        """结束会话，移入全局窗口。"""
        metrics = self.current_sessions.pop(session_id, None)
        if metrics:
            metrics.current_state = "closed"
            self.window.append(metrics)
        return metrics
    
    def global_stats(self) -> Dict:
        """全局统计（最近 window_size 个会话）。"""
        if not self.window:
            return {}
        
        total_turns = sum(m.total_turns for m in self.window)
        total_clarifications = sum(m.clarifications for m in self.window)
        total_llm = sum(m.llm_calls for m in self.window)
        total_errors = sum(m.errors for m in self.window)
        
        # 合并意图分布
        global_intent = Counter()
        for m in self.window:
            global_intent.update(m.intent_distribution)
        
        return {
            "sessions_count": len(self.window),
            "total_turns": total_turns,
            "avg_clarification_rate": total_clarifications / total_turns if total_turns else 0,
            "avg_llm_fallback_rate": total_llm / total_turns if total_turns else 0,
            "avg_error_rate": total_errors / total_turns if total_turns else 0,
            "avg_health_score": sum(m.health_score for m in self.window) / len(self.window),
            "avg_latency_ms": sum(m.avg_latency_ms for m in self.window) / len(self.window),
            "intent_distribution": dict(global_intent.most_common(5)),
        }
    
    def check_alerts(self) -> List[str]:
        """检查全局告警条件（阈值从配置文件读取，支持热更新）。"""
        alerts = []
        stats = self.global_stats()
        
        if not stats:
            return alerts
        
        self._config = self._load_config()  # 热更新配置
        
        if stats.get("avg_clarification_rate", 0) > self._get_threshold("clarification_rate_threshold", 0.3):
            alerts.append(
                "⚠️ 全局澄清率超过 %.0f%% (%.1f%%) — 建议检查意图规则覆盖度" % 
                (self._get_threshold("clarification_rate_threshold", 0.3) * 100,
                 stats["avg_clarification_rate"] * 100)
            )
        
        if stats.get("avg_llm_fallback_rate", 0) > self._get_threshold("llm_fallback_rate_threshold", 0.5):
            alerts.append(
                "⚠️ 全局 LLM 回退率超过 %.0f%% (%.1f%%) — 建议优化规则引擎或降低触发阈值" %
                (self._get_threshold("llm_fallback_rate_threshold", 0.5) * 100,
                 stats["avg_llm_fallback_rate"] * 100)
            )
        
        if stats.get("avg_error_rate", 0) > self._get_threshold("error_rate_threshold", 0.05):
            alerts.append(
                "🔴 全局错误率超过 %.0f%% (%.1f%%) — 系统可能处于异常状态" %
                (self._get_threshold("error_rate_threshold", 0.05) * 100,
                 stats["avg_error_rate"] * 100)
            )
        
        if stats.get("avg_health_score", 100) < self._get_threshold("health_score_threshold", 60):
            alerts.append(
                "🔴 全局健康度低于 %.0f (%.0f) — 建议立即检查系统状态" %
                (self._get_threshold("health_score_threshold", 60),
                 stats["avg_health_score"])
            )
        
        return alerts
```

### 4.4 AlertEngine（告警引擎）

```python
class AlertEngine:
    """
    告警引擎：基于阈值触发告警，支持去重。
    阈值从 ~/.memorygraph/config.json 读取，支持运行时热更新。
    """
    
    def __init__(self, cooldown_seconds: int = None):
        self._config = self._load_config()
        self.cooldown = cooldown_seconds or self._config.get("cooldown_seconds", 300)
        self._last_alert: Dict[str, float] = {}  # alert_key -> timestamp
    
    def _load_config(self) -> Dict:
        """加载告警配置（支持热更新，每次检查阈值前重新读取）。"""
        config_path = Path("~/.memorygraph/config.json").expanduser()
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("alerts", {})
            except (json.JSONDecodeError, OSError):
                pass
        return {}
    
    def _get_threshold(self, key: str, default: float) -> float:
        """获取当前阈值（优先从配置文件读取，默认硬编码作为 fallback）。"""
        return self._config.get("session", {}).get(key, default)
    
    def check(self, metrics: SessionMetrics) -> List[str]:
        """检查单会话告警，带冷却时间。"""
        alerts = []
        now = time.time()
        
        # 重新加载配置（支持热更新）
        self._config = self._load_config()
        
        # 告警条件（阈值从配置文件读取，默认硬编码作为 fallback）
        conditions = [
            ("clarification_rate", 
             metrics.clarification_rate > self._get_threshold("clarification_rate_threshold", 0.5), 
             "本会话澄清率过高 (%.1f%%)" % (metrics.clarification_rate * 100)),
            ("low_confidence", 
             metrics.avg_confidence < self._get_threshold("confidence_threshold", 0.3) and metrics.total_turns > 5,
             "本会话平均置信度过低 (%.2f)" % metrics.avg_confidence),
            ("high_latency", 
             metrics.latency_p95 > self._get_threshold("latency_p95_threshold", 5000),
             "本会话 95 分位延迟过高 (%.0fms)" % metrics.latency_p95),
            ("error_rate", 
             metrics.errors > 0 and metrics.total_turns > 0,
             "本会话出现 %d 次错误" % metrics.errors),
        ]
        
        for key, condition, message in conditions:
            if condition:
                alert_key = f"{metrics.session_id}:{key}"
                last_time = self._last_alert.get(alert_key, 0)
                if now - last_time > self.cooldown:
                    alerts.append(message)
                    self._last_alert[alert_key] = now
        
        return alerts
```

---

### 4.5 与持久化的观察者模式集成

```python
class MetricsObserver:
    """
    观测模块作为持久化的观察者。
    在 CLISessionPersistence.add_turn() 时自动触发指标记录，
    避免 MetricsAggregator 与持久化模块独立维护导致的数据不同步。
    """
    
    def __init__(self, aggregator: MetricsAggregator):
        self.aggregator = aggregator
    
    def on_turn_recorded(self, session_id: str, 
                           intent_category: str = "UNKNOWN",
                           execution_status: str = "ok",
                           confidence: float = 0.5,
                           total_latency_ms: float = 0,
                           llm_used: bool = False):
        """持久化模块每记录一轮对话时调用此回调。"""
        self.aggregator.record_turn(
            session_id=session_id,
            confidence=confidence,
            total_latency_ms=total_latency_ms,
            llm_used=llm_used,
            intent_category=intent_category,
            execution_status=execution_status,
        )
    
    def on_session_closed(self, session_id: str):
        """会话关闭时调用。"""
        self.aggregator.end_session(session_id)
```

在 `CLISessionPersistence` 中注册观察者（设计文档 persistence 中已预留 `register_observer` 接口）：

```python
class CLISessionPersistence:
    def __init__(self, ...):
        # ...
        self._observers: List[MetricsObserver] = []
    
    def register_observer(self, observer: MetricsObserver):
        """注册观测回调（如 MetricsObserver）。"""
        self._observers.append(observer)
    
    def add_turn(self, session_id: str, ...):
        # 保存 turn 到数据库...
        # 通知所有观察者
        for observer in self._observers:
            observer.on_turn_recorded(session_id, ...)
    
    def close_session(self, session_id: str):
        # 先 flush pending updates...
        for observer in self._observers:
            observer.on_session_closed(session_id)
        self._run(self._manager.close_session(session_id))
```

集成后优势：
- **数据一致性**：MetricsAggregator 和 CLISessionPersistence 的数据由同一事件触发，不会漏记或重复
- **解耦**：新增观测模块时只需实现 `on_turn_recorded` 接口，无需修改持久化逻辑
- **简化调用**：`run_intent_trace_with_persistence` 只需调用 `add_turn`，无需额外调用 `record_turn`

---

## 5. 日志规范

### 5.1 JSON Schema（每行一个 JSON 对象）

```json
{
  "timestamp": "2026-06-26T14:30:00.123456",
  "session_id": "cli-1782464286",
  "query": "scan 100",
  "decision_chain": {
    "pcr_expectation": "TOOL",
    "pcr_noise": 0.0,
    "pcr_complexity": 0.01,
    "intent_category": "FIND_PATTERN",
    "intent_confidence": 0.48,
    "execution_status": "ok",
    "strategy_action": null
  },
  "performance": {
    "total_latency_ms": 12.5,
    "llm_used": false,
    "llm_latency_ms": 0
  },
  "quality_signals": {
    "required_clarification": false,
    "confidence_below_threshold": true,
    "llm_fallback_triggered": false
  },
  "window_stats": {
    "total_turns": 5,
    "hot_turns": 5,
    "warm_turns": 0,
    "cold_turns": 0,
    "compressed": false,
    "estimated_tokens": 150
  }
}
```

### 5.2 日志文件组织

```
~/.memorygraph/logs/
├── decisions_20260625.jsonl      # 昨天
├── decisions_20260626.jsonl      # 今天（当前写入）
├── decisions_20260626_143000.jsonl  # 轮转文件（超过 100MB）
├── decisions_20260626_153000.jsonl  # 轮转文件
└── README.md                        # 日志格式说明
```

### 5.3 日志查询示例（命令行）

```bash
# 查看今天的高延迟轮次
$ cat ~/.memorygraph/logs/decisions_20260626.jsonl | \
  jq 'select(.performance.total_latency_ms > 100) | {query, latency: .performance.total_latency_ms}'

# 统计今天各意图分布
$ cat ~/.memorygraph/logs/decisions_20260626.jsonl | \
  jq -r '.decision_chain.intent_category' | sort | uniq -c | sort -rn

# 查找所有 LLM 回退的轮次
$ cat ~/.memorygraph/logs/decisions_20260626.jsonl | \
  jq 'select(.quality_signals.llm_fallback_triggered) | {query, action: .decision_chain.strategy_action}'
```

---

## 6. 指标与告警

### 6.1 告警阈值配置

```python
# 默认配置
DEFAULT_ALERT_CONFIG = {
    "session": {
        "clarification_rate_threshold": 0.5,    # 单会话澄清率 > 50% 告警
        "confidence_threshold": 0.3,            # 平均置信度 < 0.3 告警
        "latency_p95_threshold": 5000,          # 95 分位延迟 > 5s 告警
        "error_count_threshold": 1,             # 任何错误即告警
    },
    "global": {
        "clarification_rate_threshold": 0.3,   # 全局澄清率 > 30% 告警
        "llm_fallback_rate_threshold": 0.5,    # 全局 LLM 回退率 > 50% 告警
        "error_rate_threshold": 0.05,          # 全局错误率 > 5% 告警
        "health_score_threshold": 60,           # 健康度 < 60 告警
    },
    "cooldown_seconds": 300,  # 同一告警 5 分钟内不重复触发
}
```

### 6.2 告警级别

| 级别 | 触发条件 | 建议行动 |
|---|---|---|
| ℹ️ **INFO** | 健康度 70-80 | 观察，无需行动 |
| ⚠️ **WARNING** | 澄清率 > 30% 或 健康度 60-70 | 检查规则覆盖度 |
| 🔴 **CRITICAL** | 错误率 > 5% 或 健康度 < 60 | 立即检查系统状态 |

---

## 7. 仪表盘设计

### 7.1 实时文本仪表盘（CLI 输出）

```python
def print_session_dashboard(metrics: SessionMetrics):
    """打印单会话仪表盘。"""
    print("\n" + "="*60)
    print("  📊 会话指标仪表盘")
    print("="*60)
    print(f"  会话 ID: {metrics.session_id[:8]}...")
    print(f"  状态: {metrics.current_state} (外部: {metrics.fsm_external_state})")
    print(f"  总轮数: {metrics.total_turns}")
    print(f"  ──")
    print(f"  健康度: {metrics.health_score:.0f}/100 {'✅' if metrics.health_score > 70 else '⚠️' if metrics.health_score > 50 else '🔴'}")
    print(f"  澄清率: {metrics.clarification_rate*100:.1f}%")
    print(f"  规则命中率: {metrics.rule_hit_rate*100:.1f}%")
    print(f"  LLM 回退率: {metrics.llm_fallback_rate*100:.1f}%")
    print(f"  ──")
    print(f"  平均置信度: {metrics.avg_confidence:.2f}")
    print(f"  平均延迟: {metrics.avg_latency_ms:.0f}ms")
    print(f"  95 分位延迟: {metrics.latency_p95:.0f}ms")
    print(f"  ──")
    print(f"  意图分布:")
    for intent, count in metrics.intent_distribution.most_common(5):
        print(f"    • {intent}: {count} 次")
    print("="*60)


def print_global_dashboard(aggregator: MetricsAggregator):
    """打印全局仪表盘。"""
    stats = aggregator.global_stats()
    if not stats:
        print("[INFO] 暂无全局数据")
        return
    
    print("\n" + "="*60)
    print("  🌍 全局指标仪表盘")
    print("="*60)
    print(f"  最近会话数: {stats['sessions_count']}")
    print(f"  总轮数: {stats['total_turns']}")
    print(f"  ──")
    print(f"  平均健康度: {stats['avg_health_score']:.0f}/100")
    print(f"  平均澄清率: {stats['avg_clarification_rate']*100:.1f}%")
    print(f"  平均 LLM 回退率: {stats['avg_llm_fallback_rate']*100:.1f}%")
    print(f"  平均错误率: {stats['avg_error_rate']*100:.1f}%")
    print(f"  平均延迟: {stats['avg_latency_ms']:.0f}ms")
    print(f"  ──")
    print(f"  全局意图分布:")
    for intent, count in stats['intent_distribution'].items():
        print(f"    • {intent}: {count} 次")
    print("="*60)
    
    # 告警
    alerts = aggregator.check_alerts()
    if alerts:
        print("\n  ⚠️ 活跃告警:")
        for alert in alerts:
            print(f"    • {alert}")
    else:
        print("\n  ✅ 无告警")
```

### 7.2 输出示例

```
============================================================
  📊 会话指标仪表盘
============================================================
  会话 ID: cli-17824...
  状态: active (外部: idle)
  总轮数: 25
  ──
  健康度: 78/100 ✅
  澄清率: 12.0%
  规则命中率: 92.0%
  LLM 回退率: 8.0%
  ──
  平均置信度: 0.72
  平均延迟: 45ms
  95 分位延迟: 120ms
  ──
  意图分布:
    • TOOL: 18 次
    • ADVISOR: 5 次
    • COMPANION: 2 次
============================================================
```

---

## 8. 与 CLI 集成方案

### 8.1 新增 CLI 参数

```python
parser.add_argument("--observability", action="store_true", default=True, help="启用可观测性（默认开启）")
parser.add_argument("--no-observability", action="store_true", help="关闭可观测性")
parser.add_argument("--log-dir", type=str, default="~/.memorygraph/logs", help="日志目录")
parser.add_argument("--log-console", action="store_true", help="同时输出日志到控制台")
parser.add_argument("--alert-cooldown", type=int, default=300, help="告警冷却时间（秒）")
```

### 8.2 新增 CLI 指令

```
📝 用户输入 > stats

============================================================
  📊 会话指标仪表盘
============================================================
  ...（当前会话指标）...

📝 用户输入 > global

============================================================
  🌍 全局指标仪表盘
============================================================
  ...（最近 100 会话聚合）...

📝 用户输入 > alerts

  ⚠️ 活跃告警:
    • 全局澄清率超过 30% (35.2%) — 建议检查意图规则覆盖度

📝 用户输入 > export-metrics metrics.json

[INFO] 会话指标已导出到: metrics.json
```

### 8.3 每轮自动输出（可选）

```python
# 在每轮执行后自动打印精简指标
if observability_enabled and verbose:
    print(f"\n  [指标] 延迟: {total_latency:.0f}ms | "
          f"置信度: {parse_result.intent.confidence:.2f} | "
          f"健康度: {session_metrics.health_score:.0f}/100")
```

---

## 9. 测试策略

### 9.1 单元测试

```python
class TestSessionMetrics(unittest.TestCase):
    
    def test_health_score_calculation(self):
        """验证健康度计算公式。"""
        m = SessionMetrics(session_id="test")
        
        # 完美会话：无澄清、高置信度、无 LLM 回退
        for _ in range(10):
            m.record_turn(confidence=0.9, total_latency_ms=10, llm_used=False, 
                         required_clarification=False)
        self.assertEqual(m.health_score, 100)
        
        # 糟糕会话：50% 澄清、低置信度、50% LLM 回退
        m2 = SessionMetrics(session_id="test2")
        for _ in range(10):
            m2.record_turn(confidence=0.3, total_latency_ms=100, llm_used=True,
                          required_clarification=True)
        self.assertLess(m2.health_score, 50)
    
    def test_latency_histogram(self):
        """验证延迟直方图。"""
        m = SessionMetrics(session_id="test")
        for i in range(100):
            m.record_turn(confidence=0.8, total_latency_ms=i * 10, llm_used=False)
        
        # 95 分位应该是 95 * 10 = 950ms
        self.assertAlmostEqual(m.latency_p95, 950, delta=10)


class TestMetricsAggregator(unittest.TestCase):
    
    def test_global_stats(self):
        """验证全局统计。"""
        agg = MetricsAggregator(window_size=10)
        
        # 模拟 5 个会话
        for i in range(5):
            sid = f"sess-{i}"
            agg.start_session(sid)
            for _ in range(10):
                agg.record_turn(sid, confidence=0.8, total_latency_ms=10, 
                               llm_used=False, intent_category="TOOL")
            agg.end_session(sid)
        
        stats = agg.global_stats()
        self.assertEqual(stats["sessions_count"], 5)
        self.assertEqual(stats["total_turns"], 50)
        self.assertAlmostEqual(stats["avg_clarification_rate"], 0.0)
    
    def test_alert_threshold(self):
        """验证告警阈值。"""
        agg = MetricsAggregator()
        
        # 创建高澄清率会话
        sid = "bad-sess"
        agg.start_session(sid)
        for _ in range(10):
            agg.record_turn(sid, confidence=0.3, total_latency_ms=100,
                           llm_used=False, required_clarification=True)
        agg.end_session(sid)
        
        alerts = agg.check_alerts()
        self.assertTrue(any("澄清率" in a for a in alerts))


class TestStructuredLogger(unittest.TestCase):
    
    def test_jsonl_format(self):
        """验证输出格式为合法 JSONL。"""
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(log_dir=tmpdir)
            
            entry = DecisionLogEntry(
                timestamp="2026-06-26T14:00:00",
                session_id="test",
                query="scan 100",
                pcr_expectation="TOOL",
                pcr_noise=0.0,
                pcr_complexity=0.01,
                intent_category="FIND_PATTERN",
                intent_confidence=0.48,
                execution_status="ok",
                strategy_action=None,
                total_latency_ms=12.5,
                llm_used=False,
                llm_latency_ms=0,
                required_clarification=False,
                confidence_below_threshold=True,
                llm_fallback_triggered=False,
            )
            logger.log(entry)
            logger.close()
            
            # 读取并验证
            log_file = Path(tmpdir) / f"decisions_{datetime.now().strftime('%Y%m%d')}.jsonl"
            with open(log_file) as f:
                line = f.readline().strip()
                data = json.loads(line)
                self.assertEqual(data["session_id"], "test")
                self.assertEqual(data["query"], "scan 100")
```

### 9.2 集成测试

```python
class TestObservabilityIntegration(unittest.TestCase):
    """端到端：带观测的完整对话流程。"""
    
    def test_full_conversation_with_metrics(self):
        """
        1. 执行 10 轮对话
        2. 验证 SessionMetrics 正确累积
        3. 验证日志文件写入
        4. 验证告警触发
        """
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = StructuredLogger(log_dir=tmpdir)
            aggregator = MetricsAggregator()
            alert_engine = AlertEngine(cooldown_seconds=0)  # 无冷却，方便测试
            
            session_id = "test-sess"
            aggregator.start_session(session_id)
            
            for i in range(10):
                # 模拟执行
                pcr_output = type('obj', (object,), {'expectation': 'TOOL', 'noise_level': 0.0, 'complexity_level': 0.01})()
                parse_result = type('obj', (object,), {'intent': type('obj', (object,), {'category': 'FIND_PATTERN', 'confidence': 0.48})()})()
                
                total_latency = 15.0
                llm_used = i > 7  # 最后 2 轮触发 LLM
                
                # 记录日志
                logger.log_turn(
                    session_id=session_id,
                    query=f"query {i}",
                    pcr_output=pcr_output,
                    parse_result=parse_result,
                    execution_status="ok",
                    strategy_action=None,
                    total_latency_ms=total_latency,
                    llm_used=llm_used,
                )
                
                # 记录指标
                aggregator.record_turn(
                    session_id=session_id,
                    confidence=0.48,
                    total_latency_ms=total_latency,
                    llm_used=llm_used,
                    intent_category="FIND_PATTERN",
                )
            
            aggregator.end_session(session_id)
            
            # 验证指标
            metrics = aggregator.get_session(session_id)
            self.assertEqual(metrics.total_turns, 10)
            self.assertEqual(metrics.llm_calls, 2)
            self.assertEqual(metrics.rule_hits, 8)
            
            # 验证日志文件
            log_file = Path(tmpdir) / f"decisions_{datetime.now().strftime('%Y%m%d')}.jsonl"
            self.assertTrue(log_file.exists())
            with open(log_file) as f:
                lines = f.readlines()
            self.assertEqual(len(lines), 10)
            
            # 验证 JSON 解析
            for line in lines:
                data = json.loads(line)
                self.assertIn("session_id", data)
                self.assertIn("decision_chain", data)
```

---

## 10. 实现计划

### Phase 1: 核心日志与指标（1 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 1.1 | `observability/logger.py` | 创建 `StructuredLogger` + `DecisionLogEntry` |
| 1.2 | `observability/metrics.py` | 创建 `SessionMetrics` + `MetricsAggregator` + `AlertEngine` |
| 1.3 | `tests/test_observability_logger.py` | 日志格式、轮转、JSONL 验证 |
| 1.4 | `tests/test_observability_metrics.py` | 指标计算、告警阈值、健康度 |
| 1.5 | `tests/test_observability_integration.py` | 端到端集成测试 |

### Phase 2: CLI 集成（0.5 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 2.1 | `intent_trace_cli.py` | 注入 `StructuredLogger` + `MetricsAggregator` |
| 2.2 | `intent_trace_cli.py` | 添加 `--observability`, `--log-dir`, `--log-console` 参数 |
| 2.3 | `intent_trace_cli.py` | 添加 `stats`, `global`, `alerts`, `export-metrics` 指令 |
| 2.4 | `intent_trace_cli.py` | 每轮自动打印精简指标（延迟/置信度/健康度） |
| 2.5 | `tests/test_cli_observability.py` | CLI 观测集成测试 |

### Phase 3: 仪表盘与告警（0.5 天）

| 任务 | 文件 | 说明 |
|---|---|---|
| 3.1 | `observability/metrics.py` | 完善 `print_session_dashboard` + `print_global_dashboard` |
| 3.2 | `observability/metrics.py` | 配置化告警阈值（支持 ~/.memorygraph/config.json） |
| 3.3 | `observability/logger.py` | 日志查询工具（命令行 `mg-logs` 脚本） |
| 3.4 | `tests/test_observability_dashboard.py` | 仪表盘输出验证 |

---

## 11. 风险与回退

### 风险 1: 日志写入性能影响

**场景**：高并发时日志写入阻塞主流程。

**回退**：
1. 异步写入：使用 `asyncio.Queue` 缓冲日志，后台线程批量写入
2. 内存限制：日志队列上限 1000 条，满时丢弃旧日志（print 警告）
3. 禁用日志：`--no-observability` 完全跳过日志逻辑

### 风险 2: 磁盘空间耗尽

**场景**：日志文件无限增长，占满磁盘。

**回退**：
1. 按天切分 + 单文件 100MB 上限
2. 保留策略：默认 30 天，通过 `config.json` 配置
3. 启动时检查磁盘空间，< 1GB 时自动关闭日志

### 风险 3: 指标内存泄漏

**场景**：`MetricsAggregator.window` 的 `maxlen=100` 但每个 `SessionMetrics` 包含 `Deque` 和 `Counter`。

**回退**：
1. `window` 使用 `deque(maxlen=100)`，自动淘汰旧会话
2. `SessionMetrics` 的 `confidence_history` 和 `latency_history` 使用 `maxlen=100`，限制单会话内存
3. 估算：单会话指标 < 10KB，100 会话窗口 < 1MB

---

## 附录：文件清单

| 文件 | 状态 | 说明 |
|---|---|---|
| `agent/observability/logger.py` | 🆕 新建 | 结构化日志器 |
| `agent/observability/metrics.py` | 🆕 新建 | 指标聚合 + 告警 |
| `agent/observability/dashboard.py` | 🆕 新建 | 文本仪表盘输出 |
| `tests/test_observability_logger.py` | 🆕 新建 | 日志测试 |
| `tests/test_observability_metrics.py` | 🆕 新建 | 指标测试 |
| `tests/test_observability_integration.py` | 🆕 新建 | 集成测试 |
| `tests/test_cli_observability.py` | 🆕 新建 | CLI 集成测试 |
| `intent_trace_cli.py` | 📝 修改 | 注入观测组件 |
| `bin/mg-logs` | 🆕 新建 | 日志查询命令行工具（可选） |

---

## 设计文档体系

| 文档 | 说明 | 依赖 |
|---|---|---|
| `design_persistence.md` | 会话持久化（SQLite） | 无 |
| `design_context_window.md` | 上下文窗口管理（热/温/冷） | 读取持久化历史 |
| `design_observability.md` | 可观测性（日志/指标/告警） | 观察所有模块 |
| `design_topic_tree.md` | 话题树（对话图/回溯/分叉） | 依赖持久化 + 窗口管理 |
