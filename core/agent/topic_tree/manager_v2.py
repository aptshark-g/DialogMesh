# -*- coding: utf-8 -*-
"""
core/agent/topic_tree/manager_v2.py
───────────────────────────────────
TopicTree Manager V2 — 极致化版本。

五大极致化增强：
  1. cohesion_score:  规则 → embedding相似度 + 实体重叠度 + 意图一致性
  2. 话题决策模型:     无 → 轻量级Ψ分类器 (多特征加权决策)
  3. 分叉点识别:        cohesion阈值 → 语义相似度定位 + 意图漂移检测
  4. 合并(merge):     无 → LCA + 三路语义合并
  5. 可视化:          ASCII → ReactFlow/D3.js JSON导出

依赖（可选）:
  - sentence-transformers: 用于 embedding 计算
  - numpy: 用于向量运算
"""

from __future__ import annotations

import json
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from core.agent.topic_tree.models import TopicNode, TopicEdge, TopicEdgeType


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Embedding 引擎 (轻量级，可选依赖)
# ═══════════════════════════════════════════════════════════════════════════════

class EmbeddingEngine:
    """
    轻量级语义向量引擎。
    优先使用 sentence-transformers（离线、轻量），
    否则回退到基于 hash 的伪向量（保证功能可用）。

    编码器契约（T7）:
      - 每次 encode 都会记录当前生效的编码器身份（current_encoder()）。
      - 外部编码器（如 BGE）通过 register_encoder(name, fn) 注册，由引擎
        统一管理编码器身份与维度，避免 hash/BGE 向量混用（跨空间比较）。
      - supports_semantics() 表示当前编码器是否具备真实语义（hash 为 False）。
      - T1: 模型加载失败（含 ImportError/ValueError/TypeError 等环境问题）
        一律回退 hash 伪向量，绝不抛异常。
    """

    _model = None
    _model_name = "all-MiniLM-L6-v2"  # 384-dim, 轻量, 适合实时
    _custom_encoder: Optional[Tuple[str, Any]] = None  # (name, fn(text)->List[float])
    _encoder_name: str = "hash"       # 当前生效编码器身份
    _encoder_dim: int = 384           # 当前生效编码器维度
    _model_lock = threading.Lock()    # 2026-08-17: 防并发双载（同 semantic_encoder 修复）

    @classmethod
    def _load_model(cls):
        with cls._model_lock:
            if cls._model is not None:
                return cls._model
            try:
                # 2026-08-16: 离线优先 —— 原 SentenceTransformer(name) 联网
                # HF hub 校验（无超时, 网络受限无 CPU 挂起 180s, 实测）。本地
                # 缓存缺失时快速失败 → 编码器回退 hash。
                import os
                os.environ.setdefault("HF_HUB_OFFLINE", "1")
                os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
                from sentence_transformers import SentenceTransformer
                cls._model = SentenceTransformer(
                    cls._model_name, local_files_only=True)
                cls._encoder_name = f"sentence-transformers:{cls._model_name}"
                try:
                    cls._encoder_dim = int(cls._model.get_sentence_embedding_dimension())
                except Exception:
                    pass
                return cls._model
            except Exception:
                # T1: 宽异常兜底 — 环境导入链任何异常（ValueError/TypeError 等）都回退
                return None

    @classmethod
    def register_encoder(cls, name: str, fn) -> None:
        """注册自定义编码器（T7 契约入口，例如 BGE）。fn(text) -> List[float]。"""
        cls._custom_encoder = (name, fn)
        cls._encoder_name = name
        try:
            probe = fn("")
            if probe:
                cls._encoder_dim = len(probe)
        except Exception:
            pass

    @classmethod
    def current_encoder(cls) -> str:
        """当前生效编码器身份（hash | sentence-transformers:... | 自定义名）。"""
        return cls._encoder_name

    @classmethod
    def supports_semantics(cls) -> bool:
        """hash 伪向量不具备真实语义（跨文本相似度无意义）。"""
        return cls._encoder_name != "hash"

    @classmethod
    def reset(cls) -> None:
        """复位编码器状态（测试/热切换用）。"""
        cls._model = None
        cls._custom_encoder = None
        cls._encoder_name = "hash"
        cls._encoder_dim = 384

    @classmethod
    def encode(cls, text: str) -> List[float]:
        """编码文本为向量。失败时返回基于 hash 的确定性伪向量。"""
        if cls._custom_encoder is not None:
            name, fn = cls._custom_encoder
            try:
                vec = fn(text)
                if vec is not None and len(vec) > 0:
                    return vec
            except Exception:
                pass
            # 自定义编码器失败时回退 hash（不再尝试 sentence-transformers）
            cls._encoder_name = "hash"
            cls._encoder_dim = 384
            return cls._hash_embedding(text)
        model = cls._load_model()
        if model is not None:
            try:
                vec = model.encode(text, normalize_embeddings=True)
                return vec.tolist()
            except Exception:
                pass
        cls._encoder_name = "hash"
        cls._encoder_dim = 384
        # 回退：基于 hash 的伪向量 (384-dim, 归一化)
        return cls._hash_embedding(text)

    @staticmethod
    def _hash_embedding(text: str, dim: int = 384) -> List[float]:
        """基于 hash 的确定性伪向量。保证无外部依赖时仍可运行。"""
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # 每 4 字节生成一个 float
        vec = []
        for i in range(dim):
            idx = (i * 4) % len(h)
            val = int.from_bytes(h[idx:idx+4], "little") / (2**31 - 1)
            vec.append(val)
        # 归一化
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Cohesion 计算器 (极致化)
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_INTENT_RELATED: Dict[Tuple[str, str], float] = {
    ("ADVISOR", "QUERY"): 0.7,
    ("DIRECTIVE", "TOOL"): 0.8,
    ("COMPANION", "ADVISOR"): 0.6,
}


def intent_consistency(
    intent_a: str, intent_b: str, related: Optional[Dict[Tuple[str, str], float]] = None
) -> float:
    """模块级意图一致性计算（T5: 映射表可配置，默认见 DEFAULT_INTENT_RELATED）。"""
    if not intent_a or not intent_b:
        return 0.5  # 未知意图视为中性
    if intent_a == intent_b:
        return 1.0
    rel = related if related is not None else DEFAULT_INTENT_RELATED
    key = tuple(sorted([intent_a, intent_b]))
    return rel.get(key, 0.0)


@dataclass
class CohesionMetrics:
    """cohesion 多维度评分。"""
    semantic: float = 0.0      # embedding 余弦相似度
    entity: float = 0.0        # 实体 Jaccard 重叠度
    intent: float = 0.0        # 意图一致性 (1=相同, 0=不同)
    composite: float = 0.0     # 加权综合得分
    details: Dict[str, Any] = field(default_factory=dict)


class CohesionCalculator:
    """
    极致化 cohesion 计算：
      composite = w1 * semantic + w2 * entity + w3 * intent
    """

    def __init__(
        self,
        w_semantic: float = 0.4,
        w_entity: float = 0.35,
        w_intent: float = 0.25,
        intent_related: Optional[Dict[Tuple[str, str], float]] = None,
    ):
        self.w_semantic = w_semantic
        self.w_entity = w_entity
        self.w_intent = w_intent
        self.intent_related = dict(DEFAULT_INTENT_RELATED if intent_related is None else intent_related)

    def calculate(
        self,
        query: str,
        query_embedding: Optional[List[float]],
        query_intent: str,
        query_entities: List[Dict[str, Any]],
        target_node: TopicNode,
    ) -> CohesionMetrics:
        """计算 query 与目标节点之间的 cohesion。"""

        # 1. Semantic similarity (embedding 余弦)
        sem_score = self._semantic_similarity(query_embedding, target_node.embedding)
        # T7 编码器一致性: 目标节点嵌入与当前编码器不同空间 → 语义贡献置 0
        target_encoder = (target_node.metadata or {}).get("embedding_encoder")
        if target_encoder and target_encoder != EmbeddingEngine.current_encoder():
            sem_score = 0.0

        # 2. Entity overlap (Jaccard)
        ent_score = self._entity_overlap(query_entities, target_node.entities)

        # 3. Intent consistency
        int_score = self._intent_consistency(query_intent, target_node.intent_category)

        # Composite
        composite = (
            self.w_semantic * sem_score +
            self.w_entity * ent_score +
            self.w_intent * int_score
        )

        return CohesionMetrics(
            semantic=sem_score,
            entity=ent_score,
            intent=int_score,
            composite=round(composite, 4),
            details={
                "query": query[:50],
                "target_node": target_node.id,
                "target_name": target_node.name,
                "weights": {
                    "semantic": self.w_semantic,
                    "entity": self.w_entity,
                    "intent": self.w_intent,
                },
            },
        )

    @staticmethod
    def _semantic_similarity(
        emb_a: Optional[List[float]], emb_b: Optional[List[float]]
    ) -> float:
        if emb_a is None or emb_b is None or len(emb_a) != len(emb_b):
            return 0.0
        dot = sum(a * b for a, b in zip(emb_a, emb_b))
        # 假设已归一化
        return max(0.0, min(1.0, (dot + 1.0) / 2.0))

    @staticmethod
    def _entity_overlap(
        entities_a: List[Dict[str, Any]], entities_b: List[Dict[str, Any]]
    ) -> float:
        vals_a = set()
        for e in entities_a:
            if isinstance(e, dict):
                v = str(e.get("value", ""))
                if v:
                    vals_a.add(v)
        vals_b = set()
        for e in entities_b:
            if isinstance(e, dict):
                v = str(e.get("value", ""))
                if v:
                    vals_b.add(v)
        if not vals_a or not vals_b:
            return 0.0
        intersection = len(vals_a & vals_b)
        union = len(vals_a | vals_b)
        return intersection / union if union > 0 else 0.0

    def _intent_consistency(self, intent_a: str, intent_b: str) -> float:
        return intent_consistency(intent_a, intent_b, self.intent_related)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 话题决策分类器 Ψ (轻量级)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TopicDecision:
    """话题决策结果。"""
    action: str                      # "continue" | "fork" | "attach" | "new" | "merge"
    target_node_id: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""
    features: Dict[str, float] = field(default_factory=dict)


class TopicDecisionClassifier:
    """
    轻量级 Ψ 分类器 — 多特征加权决策。

    特征向量:
      f1: cohesion_score (综合相似度)
      f2: entity_overlap (实体重叠)
      f3: intent_drift (意图漂移度 = 1 - intent_consistency)
      f4: time_decay (时间衰减)
      f5: depth_penalty (深度惩罚)
      f6: branch_count (当前话题分支数)

    决策规则 (可替换为 sklearn 模型):
      - continue:  cohesion > 0.6, intent_drift < 0.3
      - attach:    0.3 < cohesion < 0.6, 存在历史匹配节点
      - fork:      cohesion < 0.3, 或 intent_drift > 0.5
      - merge:     检测到两个分支可合并 (语义高相似 + 意图相同)
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        thresholds: Optional[Dict[str, float]] = None,
        intent_drift_threshold: float = 0.3,
        merge_similarity: float = 0.85,
        attach_score_floor: float = 0.25,
        attach_sim_weight: float = 0.7,
        attach_recency_weight: float = 0.3,
    ):
        """T5: 全部决策阈值/权重参数化（A18 参数自适应入口）。"""
        self.weights = weights or {
            "cohesion": 0.30,
            "entity": 0.20,
            "intent_drift": 0.25,
            "time_decay": 0.10,
            "depth": 0.05,
            "branch_count": 0.10,
        }
        self.thresholds = thresholds or {
            "continue": 0.55,
            "fork": 0.30,
            "attach_min": 0.25,
        }
        self.intent_drift_threshold = intent_drift_threshold
        self.merge_similarity = merge_similarity
        self.attach_score_floor = attach_score_floor
        self.attach_sim_weight = attach_sim_weight
        self.attach_recency_weight = attach_recency_weight

    def decide(
        self,
        cohesion: CohesionMetrics,
        query: str,
        query_intent: str,
        current_node: Optional[TopicNode],
        candidate_nodes: List[TopicNode],
    ) -> TopicDecision:
        """基于多特征做出话题决策。"""

        features = self._extract_features(cohesion, current_node, candidate_nodes)

        # 意图漂移检测
        intent_drift = 1.0 - cohesion.intent

        # 决策逻辑
        if cohesion.composite >= self.thresholds["continue"] and intent_drift < self.intent_drift_threshold:
            return TopicDecision(
                action="continue",
                target_node_id=current_node.id if current_node else None,
                confidence=cohesion.composite,
                reason=(
                    f"cohesion={cohesion.composite:.2f} ≥ {self.thresholds['continue']}, "
                    f"intent_drift={intent_drift:.2f} < {self.intent_drift_threshold}"
                ),
                features=features,
            )

        # 检测是否可合并 (两个分支高度相似)
        merge_target = self._detect_merge_candidate(query, query_intent, candidate_nodes)
        if merge_target:
            return TopicDecision(
                action="merge",
                target_node_id=merge_target.id,
                confidence=merge_target.similarity,
                reason=f"检测到可合并分支: similarity={merge_target.similarity:.2f}",
                features=features,
            )

        # 检测 attach (最佳历史匹配)
        best_attach = self._find_best_attach(query, query_intent, candidate_nodes)
        if best_attach and cohesion.composite >= self.thresholds["attach_min"]:
            return TopicDecision(
                action="attach",
                target_node_id=best_attach.id,
                confidence=best_attach.score,
                reason=f"attach to {best_attach.name}: score={best_attach.score:.2f}",
                features=features,
            )

        # 默认 fork
        return TopicDecision(
            action="fork",
            target_node_id=None,
            confidence=1.0 - cohesion.composite,
            reason=f"cohesion={cohesion.composite:.2f} < {self.thresholds['attach_min']}, intent_drift={intent_drift:.2f}",
            features=features,
        )

    def _extract_features(
        self,
        cohesion: CohesionMetrics,
        current_node: Optional[TopicNode],
        candidates: List[TopicNode],
    ) -> Dict[str, float]:
        """提取决策特征向量。"""
        features = {
            "cohesion_composite": cohesion.composite,
            "cohesion_semantic": cohesion.semantic,
            "cohesion_entity": cohesion.entity,
            "cohesion_intent": cohesion.intent,
            "intent_drift": 1.0 - cohesion.intent,
            "candidate_count": float(len(candidates)),
        }
        if current_node:
            features["current_depth"] = float(current_node.depth)
            features["time_since_active"] = time.time() - current_node.last_active_at
        return features

    @dataclass
    class _Candidate:
        id: str
        name: str
        score: float
        similarity: float = 0.0

    def _detect_merge_candidate(
        self, query: str, query_intent: str, candidates: List[TopicNode]
    ) -> Optional[_Candidate]:
        """检测是否存在两个分支可合并。"""
        # 简化：找与当前 query 意图相同且语义最相似的历史节点
        best = None
        best_score = 0.0
        for node in candidates:
            if node.intent_category != query_intent:
                continue
            # 使用 embedding 计算相似度
            sim = CohesionCalculator._semantic_similarity(
                EmbeddingEngine.encode(query), node.embedding
            )
            if sim > self.merge_similarity and sim > best_score:  # 高阈值才触发合并
                best_score = sim
                best = self._Candidate(id=node.id, name=node.name, score=0.0, similarity=sim)
        return best

    def _find_best_attach(
        self, query: str, query_intent: str, candidates: List[TopicNode]
    ) -> Optional[_Candidate]:
        """找最佳 attach 目标。"""
        best = None
        best_score = 0.0
        query_emb = EmbeddingEngine.encode(query)
        for node in candidates:
            sim = CohesionCalculator._semantic_similarity(query_emb, node.embedding)
            # 时间衰减
            time_decay = 1.0 / (1.0 + (time.time() - node.last_active_at) / 3600)
            score = sim * self.attach_sim_weight + time_decay * self.attach_recency_weight
            if score > best_score and score > self.attach_score_floor:
                best_score = score
                best = self._Candidate(id=node.id, name=node.name, score=score)
        return best


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 分叉点定位器 (极致化)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ForkPoint:
    """分叉点定位结果。"""
    node_id: str
    node_name: str
    similarity: float
    intent_drift_detected: bool
    reason: str


class ForkPointLocator:
    """
    极致化分叉点定位：
      1. 语义相似度阈值：在活跃树中找最佳匹配点
      2. 意图漂移检测：如果意图类别变化 > 0.5，标记为漂移
    """

    def __init__(
        self,
        similarity_threshold: float = 0.4,
        intent_drift_threshold: float = 0.5,
        calculator: Optional[CohesionCalculator] = None,
    ):
        self.similarity_threshold = similarity_threshold
        self.intent_drift_threshold = intent_drift_threshold
        self.calculator = calculator

    def _intent_consistency(self, intent_a: str, intent_b: str) -> float:
        """意图一致性：优先用注入的 CohesionCalculator（T5 配置统一源）。"""
        if self.calculator is not None:
            return self.calculator._intent_consistency(intent_a, intent_b)
        return intent_consistency(intent_a, intent_b)

    def locate(
        self,
        query: str,
        query_intent: str,
        query_embedding: List[float],
        active_tree_nodes: List[TopicNode],
    ) -> ForkPoint:
        """
        在活跃树中定位最佳分叉点。
        返回：最佳匹配节点 (相似度最高且满足阈值)。
        """
        best_node = None
        best_score = 0.0

        for node in active_tree_nodes:
            # 语义相似度
            sim = CohesionCalculator._semantic_similarity(query_embedding, node.embedding)
            # 意图漂移检测
            intent_drift = 1.0 - self._intent_consistency(query_intent, node.intent_category)

            # 综合得分：高相似度 + 低意图漂移 才是好的分叉点
            score = sim * (1.0 - intent_drift)

            if score > best_score and sim >= self.similarity_threshold:
                best_score = score
                best_node = node

        if best_node:
            intent_drift = 1.0 - self._intent_consistency(query_intent, best_node.intent_category)
            return ForkPoint(
                node_id=best_node.id,
                node_name=best_node.name,
                similarity=best_score,
                intent_drift_detected=intent_drift >= self.intent_drift_threshold,
                reason=f"语义相似度={best_score:.2f}, 意图漂移={intent_drift:.2f}",
            )

        # 无匹配：默认在当前节点分叉
        return ForkPoint(
            node_id="",
            node_name="",
            similarity=0.0,
            intent_drift_detected=True,
            reason="无满足阈值的分叉点，在当前节点创建新分支",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 合并引擎 (LCA + 三路语义合并)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MergeResult:
    """合并结果。"""
    success: bool
    merged_node_id: Optional[str] = None
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""


class MergeEngine:
    """
    三路语义合并引擎：
      base = LCA(分支A, 分支B)
      left = 分支A 从 LCA 后的增量
      right = 分支B 从 LCA 后的增量
      合并策略：无冲突直接合并，有冲突按置信度/时间戳解决
    """

    def __init__(self, calculator: CohesionCalculator):
        self.calculator = calculator

    def find_lca(self, node_a_id: str, node_b_id: str, nodes: Dict[str, TopicNode]) -> Optional[str]:
        """找两个节点的最近公共祖先 (LCA)。"""
        # 收集 A 的所有祖先
        ancestors_a = set()
        current = nodes.get(node_a_id)
        while current:
            ancestors_a.add(current.id)
            if current.parent_id and current.parent_id in nodes:
                current = nodes[current.parent_id]
            else:
                break

        # 从 B 向上找第一个公共祖先
        current = nodes.get(node_b_id)
        while current:
            if current.id in ancestors_a:
                return current.id
            if current.parent_id and current.parent_id in nodes:
                current = nodes[current.parent_id]
            else:
                break
        return None

    def merge(
        self,
        branch_a_id: str,
        branch_b_id: str,
        nodes: Dict[str, TopicNode],
    ) -> MergeResult:
        """
        三路合并两个分支。
        """
        lca_id = self.find_lca(branch_a_id, branch_b_id, nodes)
        if lca_id is None:
            return MergeResult(success=False, summary="无公共祖先，无法合并")

        lca = nodes[lca_id]

        # 收集从 LCA 到 branch_a 的路径 (增量)
        path_a = self._collect_path(lca_id, branch_a_id, nodes)
        # 收集从 LCA 到 branch_b 的路径 (增量)
        path_b = self._collect_path(lca_id, branch_b_id, nodes)

        # 检测冲突：同一实体在不同分支中有不同值
        conflicts = self._detect_conflicts(path_a, path_b)

        if conflicts:
            # 有冲突：按置信度/时间戳解决
            resolved = self._resolve_conflicts(conflicts)
            return MergeResult(
                success=True,
                merged_node_id=lca_id,
                conflicts=resolved,
                summary=f"合并完成，LCA={lca_id}，解决 {len(resolved)} 个冲突",
            )

        # 无冲突：直接合并摘要
        merged_summary = self._merge_summaries(path_a, path_b, lca)
        return MergeResult(
            success=True,
            merged_node_id=lca_id,
            summary=merged_summary,
        )

    def _collect_path(
        self, from_id: str, to_id: str, nodes: Dict[str, TopicNode]
    ) -> List[TopicNode]:
        """收集从 from_id 到 to_id 的路径 (假设 to 是 from 的后代)。"""
        path = []
        current = nodes.get(to_id)
        while current and current.id != from_id:
            path.append(current)
            if current.parent_id and current.parent_id in nodes:
                current = nodes[current.parent_id]
            else:
                break
        path.reverse()
        return path

    def _detect_conflicts(
        self, path_a: List[TopicNode], path_b: List[TopicNode]
    ) -> List[Dict[str, Any]]:
        """检测两个路径中的实体冲突。"""
        # 收集实体值
        entities_a: Dict[str, Any] = {}
        for node in path_a:
            for e in node.entities:
                if isinstance(e, dict):
                    etype = e.get("type", "")
                    val = e.get("value", "")
                    entities_a[etype] = val

        entities_b: Dict[str, Any] = {}
        for node in path_b:
            for e in node.entities:
                if isinstance(e, dict):
                    etype = e.get("type", "")
                    val = e.get("value", "")
                    entities_b[etype] = val

        conflicts = []
        for etype in set(entities_a.keys()) & set(entities_b.keys()):
            if entities_a[etype] != entities_b[etype]:
                conflicts.append({
                    "entity_type": etype,
                    "value_a": entities_a[etype],
                    "value_b": entities_b[etype],
                    "resolution": "manual",  # 默认需要人工确认
                })
        return conflicts

    def _resolve_conflicts(self, conflicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """自动解决冲突 (简化版：取时间戳最新的)。"""
        resolved = []
        for c in conflicts:
            # 简化：标记为需人工确认，但提供建议
            c["resolution"] = "manual"
            c["suggestion"] = f"实体 '{c['entity_type']}' 存在分歧，请确认使用哪个值"
            resolved.append(c)
        return resolved

    def _merge_summaries(
        self, path_a: List[TopicNode], path_b: List[TopicNode], lca: TopicNode
    ) -> str:
        """合并两个分支的摘要。"""
        summaries = [lca.summary] if lca.summary else []
        for node in path_a:
            if node.summary:
                summaries.append(node.summary)
        for node in path_b:
            if node.summary and node.summary not in summaries:
                summaries.append(node.summary)
        return "；".join(summaries[:5])  # 最多保留 5 句


# ═══════════════════════════════════════════════════════════════════════════════
# 7. ReactFlow / D3.js 导出器
# ═══════════════════════════════════════════════════════════════════════════════

class ReactFlowExporter:
    """
    将 TopicTree 导出为 ReactFlow 兼容的 JSON 格式。
    """

    @staticmethod
    def export(
        nodes: Dict[str, TopicNode],
        edges: List[TopicEdge],
        current_node_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        导出为 ReactFlow 格式:
          { nodes: [...], edges: [...] }
        """
        rf_nodes = []
        rf_edges = []

        # 计算布局：简单的层级布局 (y = depth * 100, x =  sibling_index * 200)
        depth_groups: Dict[int, List[str]] = {}
        for node in nodes.values():
            depth_groups.setdefault(node.depth, []).append(node.id)

        for depth, node_ids in depth_groups.items():
            for idx, node_id in enumerate(node_ids):
                node = nodes[node_id]
                is_current = node_id == current_node_id
                rf_nodes.append({
                    "id": node_id,
                    "type": "topicNode",
                    "position": {"x": idx * 250, "y": depth * 150},
                    "data": {
                        "label": node.name or f"Node {node_id}",
                        "summary": node.summary,
                        "intent": node.intent_category,
                        "entity_count": len(node.entities),
                        "is_current": is_current,
                        "is_summary": node.metadata.get("is_summary", False),
                    },
                    "style": {
                        "background": "#ff6b6b" if is_current else ("#eee" if node.metadata.get("is_summary") else "#fff"),
                        "border": "2px solid #333" if is_current else "1px solid #ccc",
                        "width": 180,
                    },
                })

        # 边：parent-child + 其他类型
        for edge in edges:
            rf_edges.append({
                "id": f"e-{edge.source_id}-{edge.target_id}",
                "source": edge.source_id,
                "target": edge.target_id,
                "label": edge.edge_type.value,
                "type": "smoothstep",
                "animated": edge.edge_type == TopicEdgeType.TEMPORAL,
                "style": {
                    "stroke": "#888" if edge.edge_type == TopicEdgeType.PARENT_CHILD else "#4ecdc4",
                    "strokeWidth": 2 if edge.edge_type == TopicEdgeType.PARENT_CHILD else 1,
                },
            })

        return {"nodes": rf_nodes, "edges": rf_edges}

    @staticmethod
    def to_html(nodes: Dict[str, TopicNode], edges: List[TopicEdge], current_node_id: Optional[str] = None) -> str:
        """生成包含 D3.js 树状图的可视化 HTML 字符串。"""
        data = ReactFlowExporter.export(nodes, edges, current_node_id)
        return json.dumps(data, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. 极致化 TopicTree 管理器
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RoutingDecisionV2:
    """V2 路由决策结果。"""
    action: str                      # "continue" | "fork" | "attach" | "new" | "merge"
    target_node_id: Optional[str] = None
    cohesion_score: float = 0.0
    confidence: float = 0.0
    reason: str = ""
    features: Dict[str, Any] = field(default_factory=dict)
    fork_point: Optional[ForkPoint] = None
    merge_result: Optional[MergeResult] = None


DEFAULT_TOPIC_TREE_CONFIG: Dict[str, Any] = {
    # T5: 阈值/权重统一参数化（A18 参数自适应入口；默认值 = 原硬编码）
    "cohesion_continue": 0.55,
    "cohesion_fork": 0.25,
    "max_depth": 6,
    "hot_zone_depth": 2,
    "activation_threshold": 10,
    "auto_activate": True,          # T6: 默认首轮 route 即建树（不再静默跳过）
    "cohesion_weights": {"w_semantic": 0.4, "w_entity": 0.35, "w_intent": 0.25},
    "intent_related": None,
    "classifier_weights": None,
    "classifier_thresholds": None,
    "intent_drift_threshold": 0.3,
    "merge_similarity": 0.85,
    "attach_score_floor": 0.25,
    "fork_similarity_threshold": 0.4,
    "fork_intent_drift_threshold": 0.5,
}


class TopicTreeManagerV2:
    """
    TopicTree 管理器 V2 — 极致化版本。

    集成五大增强：
      1. 多维度 cohesion (embedding + entity + intent)
      2. Ψ 分类器 (轻量级多特征决策)
      3. 语义分叉点定位 + 意图漂移检测
      4. LCA + 三路语义合并
      5. ReactFlow/D3.js 导出
    """

    # 阈值（默认值；实例值由 config 覆盖 — T5 参数化）
    COHESION_CONTINUE = DEFAULT_TOPIC_TREE_CONFIG["cohesion_continue"]
    COHESION_FORK = DEFAULT_TOPIC_TREE_CONFIG["cohesion_fork"]
    MAX_DEPTH = DEFAULT_TOPIC_TREE_CONFIG["max_depth"]
    HOT_ZONE_DEPTH = DEFAULT_TOPIC_TREE_CONFIG["hot_zone_depth"]
    ACTIVATION_THRESHOLD = DEFAULT_TOPIC_TREE_CONFIG["activation_threshold"]

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._nodes: Dict[str, TopicNode] = {}
        self._edges: List[TopicEdge] = []
        self._current_node_id: Optional[str] = None
        self._root_id: Optional[str] = None
        self._entity_index: Dict[str, Set[str]] = {}
        self._hot_zone: Set[str] = set()

        # T5: 配置合并（默认 + 外部覆盖），实例阈值从此读取
        cfg = dict(DEFAULT_TOPIC_TREE_CONFIG)
        if config:
            cfg.update(config)
        self.config = cfg
        self.cohesion_continue = float(cfg["cohesion_continue"])
        self.cohesion_fork = float(cfg["cohesion_fork"])
        self.max_depth = int(cfg["max_depth"])
        self.hot_zone_depth = int(cfg["hot_zone_depth"])
        self.activation_threshold = int(cfg["activation_threshold"])
        self.auto_activate = bool(cfg.get("auto_activate", True))

        # 极致化组件
        cw = cfg.get("cohesion_weights") or {}
        self.cohesion_calculator = CohesionCalculator(
            w_semantic=float(cw.get("w_semantic", 0.4)),
            w_entity=float(cw.get("w_entity", 0.35)),
            w_intent=float(cw.get("w_intent", 0.25)),
            intent_related=cfg.get("intent_related"),
        )
        self.decision_classifier = TopicDecisionClassifier(
            weights=cfg.get("classifier_weights"),
            thresholds=cfg.get("classifier_thresholds"),
            intent_drift_threshold=float(cfg.get("intent_drift_threshold", 0.3)),
            merge_similarity=float(cfg.get("merge_similarity", 0.85)),
            attach_score_floor=float(cfg.get("attach_score_floor", 0.25)),
        )
        self.fork_locator = ForkPointLocator(
            similarity_threshold=float(cfg.get("fork_similarity_threshold", 0.4)),
            intent_drift_threshold=float(cfg.get("fork_intent_drift_threshold", 0.5)),
            calculator=self.cohesion_calculator,
        )
        self.merge_engine = MergeEngine(self.cohesion_calculator)
        self.exporter = ReactFlowExporter()

        # 统计
        self._turn_count = 0
        self._is_active = False
        self._potential_forks: List[Dict[str, Any]] = []

    # ── 激活控制 ─────────────────────────────────────────────────

    def activate(self, history: List[Any]) -> None:
        """激活 TopicTree。"""
        self._is_active = True

    def is_active(self) -> bool:
        return self._is_active

    def should_activate(self, turn_index: int) -> bool:
        return turn_index >= self.activation_threshold

    def mark_potential_fork(
        self, turn_index: int, query: str, cohesion_score: float, intent_category: str
    ) -> None:
        """标记潜在分叉点 (延迟激活期间)。"""
        self._potential_forks.append({
            "turn_index": turn_index,
            "query": query[:50],
            "cohesion_score": cohesion_score,
            "intent_category": intent_category,
        })

    # ── 核心路由 (极致化) ─────────────────────────────────────────

    def route(
        self,
        query: str,
        turn_index: int,
        cohesion_score: Optional[float] = None,  # 保留兼容旧接口
        extracted_entities: Optional[List[Dict[str, Any]]] = None,
        query_intent: str = "",
    ) -> RoutingDecisionV2:
        """
        极致化话题路由。
        """
        if not self._is_active:
            if self.auto_activate:
                # T6: 默认首轮即建树（discourse_manager 显式 activate 不受影响）
                self.activate([])
            else:
                return RoutingDecisionV2(
                    action="continue", reason="TopicTree not yet activated",
                )

        self._turn_count += 1

        # 1. 计算 query embedding (缓存)
        query_embedding = EmbeddingEngine.encode(query)

        # 2. 计算与当前节点的多维度 cohesion
        current_node = self._nodes.get(self._current_node_id) if self._current_node_id else None
        if current_node:
            cohesion = self.cohesion_calculator.calculate(
                query=query,
                query_embedding=query_embedding,
                query_intent=query_intent,
                query_entities=extracted_entities or [],
                target_node=current_node,
            )
        else:
            cohesion = CohesionMetrics(composite=0.0)

        # 3. Ψ 分类器决策
        candidate_nodes = [n for n in self._nodes.values() if n.id != self._current_node_id]
        decision = self.decision_classifier.decide(
            cohesion=cohesion,
            query=query,
            query_intent=query_intent,
            current_node=current_node,
            candidate_nodes=candidate_nodes,
        )

        # 4. 执行决策
        if decision.action == "continue":
            result = self._execute_continue(current_node, query, query_intent, query_embedding, extracted_entities)

        elif decision.action == "fork":
            # 极致化：分叉点定位
            active_nodes = list(self._nodes.values())
            fork_point = self.fork_locator.locate(query, query_intent, query_embedding, active_nodes)
            result = self._execute_fork(query, query_intent, query_embedding, extracted_entities, fork_point)

        elif decision.action == "attach":
            result = self._execute_attach(decision.target_node_id, query, query_intent, query_embedding, extracted_entities)

        elif decision.action == "merge":
            result = self._execute_merge(decision.target_node_id, query, query_intent, query_embedding, extracted_entities)

        else:
            result = self._execute_new(query, query_intent, query_embedding, extracted_entities)

        # 补充特征信息
        result.cohesion_score = cohesion.composite
        result.confidence = decision.confidence
        result.features = {
            "cohesion": cohesion.to_dict() if hasattr(cohesion, "to_dict") else {
                "semantic": cohesion.semantic,
                "entity": cohesion.entity,
                "intent": cohesion.intent,
                "composite": cohesion.composite,
            },
            "decision_features": decision.features,
        }
        return result

    # ── 执行动作 ─────────────────────────────────────────────────

    def _execute_continue(
        self, current_node: Optional[TopicNode], query: str, intent: str, embedding: List[float], entities: Optional[List[Dict]]
    ) -> RoutingDecisionV2:
        if current_node is None:
            return self._execute_new(query, intent, embedding, entities)
        current_node.last_active_at = time.time()
        return RoutingDecisionV2(
            action="continue", target_node_id=current_node.id,
            reason="continue current topic",
        )

    def _execute_fork(
        self, query: str, intent: str, embedding: List[float], entities: Optional[List[Dict]], fork_point: ForkPoint
    ) -> RoutingDecisionV2:
        # 分叉点定位：在最佳匹配节点下创建分支
        parent_id = fork_point.node_id if fork_point.node_id and fork_point.node_id in self._nodes else self._current_node_id
        if parent_id is None:
            return self._execute_new(query, intent, embedding, entities)

        parent = self._nodes[parent_id]
        new_node = self._create_node(
            name=self._extract_topic_name(query),
            parent_id=parent_id,
            entities=entities or [],
            embedding=embedding,
            intent=intent,
            summary=query[:80],  # 简化：用 query 前 80 字作为摘要
        )
        # 标记意图漂移
        if fork_point.intent_drift_detected:
            new_node.metadata["intent_drift"] = True
            new_node.metadata["drift_reason"] = fork_point.reason

        self._add_edge(parent_id, new_node.id, TopicEdgeType.PARENT_CHILD, metadata={"fork": True})
        self._current_node_id = new_node.id
        self._maintain_hot_zone(new_node.id)
        self._check_depth_and_compress(new_node.id)

        return RoutingDecisionV2(
            action="fork", target_node_id=new_node.id,
            reason=f"fork at {fork_point.node_name or 'current'}: {fork_point.reason}",
            fork_point=fork_point,
        )

    def _execute_attach(
        self, target_id: Optional[str], query: str, intent: str, embedding: List[float], entities: Optional[List[Dict]]
    ) -> RoutingDecisionV2:
        if target_id is None or target_id not in self._nodes:
            return self._execute_fork(query, intent, embedding, entities, ForkPoint(reason="attach target not found, fallback to fork"))
        node = self._nodes[target_id]
        node.last_active_at = time.time()
        node.embedding = embedding  # 更新 embedding
        self._current_node_id = target_id
        self._maintain_hot_zone(target_id)
        return RoutingDecisionV2(
            action="attach", target_node_id=target_id,
            reason="attach to existing topic",
        )

    def _execute_merge(
        self, target_id: Optional[str], query: str, intent: str, embedding: List[float], entities: Optional[List[Dict]]
    ) -> RoutingDecisionV2:
        if target_id is None or target_id not in self._nodes or self._current_node_id is None:
            return self._execute_attach(target_id, query, intent, embedding, entities)

        merge_result = self.merge_engine.merge(self._current_node_id, target_id, self._nodes)
        if merge_result.success:
            # 合并后切换到 LCA 节点
            self._current_node_id = merge_result.merged_node_id
            return RoutingDecisionV2(
                action="merge", target_node_id=merge_result.merged_node_id,
                reason=merge_result.summary, merge_result=merge_result,
            )
        else:
            return self._execute_attach(target_id, query, intent, embedding, entities)

    def _execute_new(
        self, query: str, intent: str, embedding: List[float], entities: Optional[List[Dict]]
    ) -> RoutingDecisionV2:
        new_node = self._create_node(
            name=self._extract_topic_name(query) or "root",
            parent_id=None,
            entities=entities or [],
            embedding=embedding,
            intent=intent,
            summary=query[:80],
        )
        self._root_id = new_node.id
        self._current_node_id = new_node.id
        self._maintain_hot_zone(new_node.id)
        return RoutingDecisionV2(
            action="new", target_node_id=new_node.id,
            reason="new root topic",
        )

    # ── 节点管理 (V2 增强) ─────────────────────────────────────────

    def _create_node(
        self, name: str, parent_id: Optional[str], entities: List[Dict[str, Any]],
        embedding: Optional[List[float]] = None, intent: str = "", summary: str = "",
    ) -> TopicNode:
        node = TopicNode(
            name=name,
            parent_id=parent_id,
            entities=entities,
            embedding=embedding,
            intent_category=intent,
            summary=summary,
            depth=0 if parent_id is None else self._nodes[parent_id].depth + 1,
        )
        # T7: 节点标记编码器身份/维度，跨空间比较由 CohesionCalculator 置 0
        node.metadata["embedding_encoder"] = EmbeddingEngine.current_encoder()
        node.metadata["embedding_dim"] = len(embedding) if embedding else 0
        self._nodes[node.id] = node
        if parent_id and parent_id in self._nodes:
            self._nodes[parent_id].children_ids.append(node.id)
        for entity in entities:
            if isinstance(entity, dict):
                val = str(entity.get("value", ""))
                if val:
                    self._entity_index.setdefault(val, set()).add(node.id)
        return node

    def _add_edge(self, source_id: str, target_id: str, edge_type: TopicEdgeType, weight: float = 1.0, metadata: Optional[Dict] = None) -> TopicEdge:
        edge = TopicEdge(source_id=source_id, target_id=target_id, edge_type=edge_type, weight=weight, metadata=metadata or {})
        self._edges.append(edge)
        return edge

    # ── 热区 / 深度 (继承 V1) ───────────────────────────────────────

    def _maintain_hot_zone(self, current_node_id: str) -> None:
        self._hot_zone.clear()
        self._hot_zone.add(current_node_id)
        ancestors = self._get_ancestors(current_node_id, depth=self.hot_zone_depth)
        for node in ancestors:
            self._hot_zone.add(node.id)
        current = self._nodes.get(current_node_id)
        if current:
            for child_id in current.children_ids:
                self._hot_zone.add(child_id)

    def _get_ancestors(self, node_id: str, depth: int = 2) -> List[TopicNode]:
        ancestors = []
        current = self._nodes.get(node_id)
        count = 0
        while current and current.parent_id and count < depth:
            parent = self._nodes.get(current.parent_id)
            if parent:
                ancestors.append(parent)
                current = parent
                count += 1
            else:
                break
        return list(reversed(ancestors))

    def _check_depth_and_compress(self, node_id: str) -> None:
        path = self._get_path_to_root(node_id)
        if len(path) <= self.max_depth:
            return
        mid = len(path) // 2
        summary_node = self._create_summary_node(path[:mid])
        for node in path[mid:]:
            node.parent_id = summary_node.id
            summary_node.children_ids.append(node.id)
        if path[0].parent_id is None:
            self._root_id = summary_node.id
        self._update_depth_recursive(summary_node.id, 0)

    def _get_path_to_root(self, node_id: str) -> List[TopicNode]:
        path = []
        current = self._nodes.get(node_id)
        while current:
            path.append(current)
            if current.parent_id and current.parent_id in self._nodes:
                current = self._nodes[current.parent_id]
            else:
                break
        return list(reversed(path))

    def _update_depth_recursive(self, node_id: str, depth: int) -> None:
        node = self._nodes.get(node_id)
        if not node:
            return
        node.depth = depth
        for child_id in node.children_ids:
            self._update_depth_recursive(child_id, depth + 1)

    def _create_summary_node(self, nodes_to_compress: List[TopicNode]) -> TopicNode:
        if not nodes_to_compress:
            return self._create_node(name="summary", parent_id=None, entities=[])
        all_entities = []
        name_parts = []
        for node in nodes_to_compress:
            all_entities.extend(node.entities)
            if node.name and node.name not in name_parts:
                name_parts.append(node.name)
        summary_name = " | ".join(name_parts[:3]) + "..." if len(name_parts) > 3 else " | ".join(name_parts)
        return self._create_node(
            name=f"[摘要] {summary_name}",
            parent_id=nodes_to_compress[0].parent_id,
            entities=all_entities,
            summary=f"压缩了 {len(nodes_to_compress)} 个节点",
        )

    def _extract_topic_name(self, query: str) -> str:
        query = query.strip()
        if len(query) <= 20:
            return query
        return query[:20] + "..."

    # ── 导出 ─────────────────────────────────────────────────────

    def to_reactflow(self) -> Dict[str, Any]:
        """导出为 ReactFlow JSON。"""
        return self.exporter.export(self._nodes, self._edges, self._current_node_id)

    def to_d3_json(self) -> str:
        """导出为 D3.js 树状图 JSON。"""
        return self.exporter.to_html(self._nodes, self._edges, self._current_node_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
            "edges": [e.to_dict() for e in self._edges],
            "current_node_id": self._current_node_id,
            "root_id": self._root_id,
            "is_active": self._is_active,
            "turn_count": self._turn_count,
            "potential_forks": self._potential_forks,
        }

    # ── 查询 API ─────────────────────────────────────────────────

    def get_current_node(self) -> Optional[TopicNode]:
        return self._nodes.get(self._current_node_id)

    def get_current_branch(self) -> List[TopicNode]:
        """返回从根到当前节点的活跃分支（root→current）。

        T2 修复: context_assembly 曾调用不存在的方法导致 topic_tree 上下文恒空。
        无树时返回空列表（不抛异常）。
        """
        if not self._current_node_id:
            return []
        return self._get_path_to_root(self._current_node_id)

    def get_active_path(self) -> List[TopicNode]:
        """get_current_branch 别名（T3 修复: engineering TopicTreeBridge 曾调
        get_active_path 不存在 → 恒空）。"""
        return self.get_current_branch()

    def get_node(self, node_id: str) -> Optional[TopicNode]:
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> List[TopicNode]:
        return list(self._nodes.values())

    def get_tree_summary(self) -> Dict[str, Any]:
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "current_node_id": self._current_node_id,
            "root_id": self._root_id,
            "max_depth": max((n.depth for n in self._nodes.values()), default=0),
            "hot_zone_size": len(self._hot_zone),
            "is_active": self._is_active,
            "turn_count": self._turn_count,
        }
