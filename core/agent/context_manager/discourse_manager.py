# core/agent/context_manager/discourse_manager.py
"""DiscourseManager —— 统一入口，整合三级协同 + 用户识别 + 任务引擎。

职责：
1. 用户识别：加载用户画像，注入用户偏好到查询
2. 模式路由：根据复杂度自动选择 rule/small_model/remote_llm
3. 话语块处理：调用 DiscoursePipeline 处理输入
4. 任务检测：检测任务类型和状态，关联话语块
5. 上下文组装：Hot/Warm/Cold + 任务上下文 + 用户画像上下文
6. 特征提取：更新用户画像（技术水平、领域偏好等）
7. 持久化：会话保存、用户画像保存

使用方式：
    manager = DiscourseManager(user_id="user_123", mode="auto")
    context = manager.process_turn("帮我写 Python 代码", turn_index=0)

    # 获取任务状态
    tasks = manager.get_tasks()
    print(manager.get_task_summary(tasks[0].task_id))

    # 获取用户画像
    profile = manager.get_user_profile()
    print(profile.tech_level, profile.domains)

    # 保存会话
    manager.save_session("/path/to/session.json")
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

try:
    from core.agent.context_manager.semantic_index import SemanticIndex
except ImportError:
    SemanticIndex = None  # type: ignore

try:
    from core.agent.context_manager.turn import Turn, ContextBlock
    from core.agent.context_manager.context_layer import ContextLayer
except ImportError:
    Turn = None  # type: ignore
    ContextBlock = None  # type: ignore
    ContextLayer = None  # type: ignore

try:
    from core.agent.user_engine.consistency_checker import ConsistencyChecker
except ImportError:
    ConsistencyChecker = None  # type: ignore

try:
    from core.agent.v3_common.discourse_integration import DiscoursePipeline
except ImportError:
    DiscoursePipeline = None  # type: ignore

try:
    from core.agent.coordinator.mode_router import ModeRouter, ProcessingMode
    from core.agent.coordinator.small_model_client import get_small_model_client
except ImportError:
    ModeRouter = None  # type: ignore
    ProcessingMode = None  # type: ignore
    get_small_model_client = None  # type: ignore

try:
    from core.agent.user_engine import UserManager, UserExtractor, UserProfile
except ImportError:
    UserManager = None  # type: ignore
    UserExtractor = None  # type: ignore
    UserProfile = None  # type: ignore

try:
    from core.agent.task_engine import TaskManager, Task
except ImportError:
    TaskManager = None  # type: ignore
    Task = None  # type: ignore

try:
    from core.agent.v3_common.serialization import save_session as _save_session, load_session as _load_session
except ImportError:
    _save_session = None  # type: ignore
    _load_session = None  # type: ignore

logger = logging.getLogger(__name__)


class DiscourseManager:
    """统一上下文管理器 —— 支持语义搜索与跨会话引用。"""

    def __init__(
        self,
        user_id: Optional[str] = None,
        session_id: str = "default",
        mode: str = "auto",  # auto / rule / small_model / remote_llm
        cost_budget: str = "standard",  # free / standard / premium
        preload: bool = False,
    ):
        self.user_id = user_id or "anonymous"
        self.session_id = session_id
        self.mode = mode
        self.cost_budget = cost_budget

        # 初始化组件
        self._init_components()

        # 预加载（可选）
        if preload:
            self.preload()

    def _init_components(self):
        """初始化所有子组件。"""
        # 1. 小模型客户端（共享单例）
        sm_client = get_small_model_client() if get_small_model_client else None

        # 2. 模式路由器
        if ModeRouter:
            self.router = ModeRouter(
                small_model_client=sm_client,
                force_mode=self.mode if self.mode != "auto" else None,
                cost_budget=self.cost_budget,
            )
        else:
            self.router = None

        # 3. 话语块管道
        if DiscoursePipeline:
            self.pipeline = DiscoursePipeline(
                session_id=self.session_id,
                hot_turns=5,
                enabled=True,
            )
        else:
            self.pipeline = None

        # 4. 语义索引（Phase 3：跨会话块搜索）
        if SemanticIndex:
            self.semantic_index = SemanticIndex()
        else:
            self.semantic_index = None

        # 5. 用户引擎
        if UserManager and UserExtractor:
            self.user_manager = UserManager()
            self.user_extractor = UserExtractor(sm_client)
            self.user_profile = self.user_manager.get_or_create(self.user_id)
        else:
            self.user_manager = None
            self.user_extractor = None
            self.user_profile = None

        # 6. 任务引擎
        if TaskManager:
            self.task_manager = TaskManager(sm_client)
        else:
            self.task_manager = None

        # 7. 上下文层（重构：注入前缀不污染原始查询）
        if ContextLayer:
            self.context_layer = ContextLayer()
        else:
            self.context_layer = None

        # 8. 一致性校验器（对抗性输入防护）
        if ConsistencyChecker:
            self.consistency_checker = ConsistencyChecker(min_history=3, window_size=5)
        else:
            self.consistency_checker = None

        # 9. 跨会话块索引（block_id → DiscourseBlock，用于引用）
        self._global_block_index: Dict[str, Any] = {}

        # 10. 会话状态
        self.turn_count = 0
        self._turn_history: List[Any] = []  # 保存最近 N 个 Turn 用于一致性校验
        
        # 话题树：同话题的 Turn 聚合到同一分支
        self._current_topic_id = 0
        self._topic_tree: Dict[int, Dict[str, Any]] = {}  # topic_id -> {name, turns, domains, intent, start_idx, end_idx}
        self._node_id_to_topic_id: Dict[str, int] = {}  # TopicTreeManagerV2 node_id -> topic_id

        # 11. 话题树 V2（极致化话题图，embedding + 实体 + 意图三维 cohesion）
        # 设置离线模式，避免 HuggingFace 下载超时
        import os
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            from core.agent.topic_tree.manager_v2 import TopicTreeManagerV2, EmbeddingEngine
            # Monkey-patch EmbeddingEngine._load_model 直接返回 None（避免 sentence-transformers 下载）
            def _fast_load_model(cls):
                return None
            EmbeddingEngine._load_model = classmethod(_fast_load_model)
            EmbeddingEngine._model = None
            self._topic_tree_v2 = TopicTreeManagerV2()
            self._topic_tree_v2.activate([])
            self._topic_tree_v2_available = True
            
            # 用 BGE 编码器替代 hash 回退（提升 TopicTreeManagerV2 精度）
            if self.semantic_index:
                try:
                    encoder = self.semantic_index._get_encoder()
                    # 强制初始化编码器（懒加载）
                    if encoder and not getattr(encoder, '_initialized', False):
                        try:
                            encoder.encode("初始化")
                        except Exception:
                            pass
                    
                    if encoder:
                        import numpy as np
                        def _bge_encode(text):
                            try:
                                vec = encoder.encode(text)
                                if vec is not None and len(vec) > 0:
                                    vec = np.squeeze(vec)
                                    norm = np.linalg.norm(vec)
                                    if norm > 0:
                                        vec = vec / norm
                                    return vec.tolist()
                            except Exception:
                                pass
                            return EmbeddingEngine._hash_embedding(text)
                        EmbeddingEngine.encode = staticmethod(_bge_encode)
                        logger.info("TopicTreeManagerV2 using BGE encoder (512-dim) instead of hash fallback")
                except Exception as e:
                    logger.warning(f"Failed to patch BGE encoder for TopicTreeManagerV2: {e}")
        except Exception as e:
            logger.warning(f"TopicTreeManagerV2 not available: {e}")
            self._topic_tree_v2 = None
            self._topic_tree_v2_available = False

        logger.info(
            f"DiscourseManager initialized: user={self.user_id}, "
            f"mode={self.mode}, cost_budget={self.cost_budget}, "
            f"topic_tree_v2={self._topic_tree_v2_available}"
        )

        # P1: 自动恢复之前的会话数据
        self._restore_session()


    # ── 核心接口 ──────────────────────────────────────────────────

    def process_turn(self, query: str, turn_index: Optional[int] = None) -> str:
        """处理单轮输入，返回上下文字符串（Turn 驱动架构）。

        重构后流程：
        1. 创建 Turn（保存原始查询，不修改）
        2. 上下文层注入（用户画像、任务状态 → ContextBlock，不污染 raw_query）
        3. 一致性校验（跨轮行为 vs 自我描述）
        4. 模式路由（基于 Turn 的 router_context）
        5. 话语块处理（在 Turn.raw_query 上分割）
        6. 任务检测（分析 Turn.raw_query）
        7. 语义索引（只索引 Turn.raw_query）
        8. 记录轮次统计（每 Turn 只调用一次）
        9. 组装最终上下文（ContextBlock + 话语块）
        """
        if turn_index is None:
            turn_index = self.turn_count
        self.turn_count = max(self.turn_count, turn_index + 1)

        start_time = time.time()

        # 1. 创建 Turn（原始查询不可修改）
        if Turn:
            turn = Turn(turn_index=turn_index, raw_query=query)
        else:
            # 回退：旧方式（字符串拼接）
            return self._process_turn_legacy(query, turn_index)

        # 2. 上下文层注入（不污染 raw_query）
        if self.context_layer is not None:
            self.context_layer.inject_for_router(turn, self.user_profile, self.task_manager)
            # 为 LLM 组装完整上下文（如果需要）
            llm_blocks = self.context_layer.inject_for_llm(turn, self.user_profile, self.task_manager)
            for block in llm_blocks:
                turn.add_context(block)

        # 3. 用户特征提取 + 一致性校验
        self._extract_and_update_user_features(turn)

        # 4. 模式路由（基于 Turn 的上下文，不污染文本）
        routed_mode = self._route_mode(turn, turn_index)
        turn.metadata.router_mode = routed_mode.value if hasattr(routed_mode, "value") else str(routed_mode)
        logger.info(f"Processing mode: {turn.metadata.router_mode}")

        # 5. 话语块处理（在干净文本上分割）
        blocks_before = 0
        if self.pipeline and hasattr(self.pipeline, 'manager'):
            blocks_before = len(self.pipeline.manager.get_blocks())
        
        if routed_mode == (ProcessingMode.REMOTE_LLM if ProcessingMode else False):
            context = self.pipeline.process_turn(turn.raw_query, turn_index=turn_index)
        elif routed_mode == (ProcessingMode.SMALL_MODEL if ProcessingMode else False):
            context = self._process_with_small_model(turn.raw_query, turn_index)
        else:
            context = self.pipeline.process_turn(turn.raw_query, turn_index=turn_index)

        # 5b. 保存话语块到 Turn（只记录本次新增的块）
        if self.pipeline and hasattr(self.pipeline, 'manager'):
            all_blocks = self.pipeline.manager.get_blocks()
            blocks_after = len(all_blocks)
            if blocks_after > blocks_before:
                turn.discourse_blocks = all_blocks[blocks_before:blocks_after]
            else:
                # 没有新增块：用当前查询创建新块，避免累积污染
                turn.discourse_blocks = []
            
            # 调试：验证块数量
            logger.debug(f"Turn {turn_index}: {len(turn.discourse_blocks)} new blocks (total {blocks_after}, before {blocks_before})")

        # 6. 任务检测（分析干净文本）
        if self.task_manager and self.pipeline:
            latest_block = self.pipeline.manager.get_latest_block()
            if latest_block:
                self.task_manager.detect_and_update(
                    query=turn.raw_query,  # 干净文本！
                    block_id=latest_block.id,
                    turn_index=turn_index,
                    intent_label=getattr(latest_block, 'intent_label', None),
                )
                # 记录轮次（每 Turn 只一次）
                self._record_turn_once(turn, latest_block)

        # 7. 语义索引（只索引干净文本，不污染！）
        if self.semantic_index and self.pipeline and hasattr(self.pipeline, 'manager'):
            try:
                latest_block = self.pipeline.manager.get_latest_block()
                if latest_block:
                    block_id = getattr(latest_block, 'id', None)
                    # 索引干净文本（不含上下文注入）
                    clean_text = self.context_layer.inject_for_search(turn) if self.context_layer else turn.raw_query
                    if block_id and clean_text and block_id not in self._global_block_index:
                        if self.semantic_index.add_block(block_id, clean_text):
                            self._global_block_index[block_id] = latest_block
                            logger.debug(f"Indexed block {block_id} (clean text, len={len(clean_text)})")
            except Exception as e:
                logger.debug(f"Block indexing skipped: {e}")

        # 8. 保存 Turn 到历史（用于一致性校验）
        self._turn_history.append(turn)
        if len(self._turn_history) > 20:
            self._turn_history.pop(0)

        # 9. 组装最终上下文（含 ContextBlock + 话语块）
        final_context = self._assemble_context(turn, context, turn_index)

        latency = time.time() - start_time
        turn.metadata.latency_ms = latency * 1000
        logger.info(f"Turn {turn_index} processed in {latency:.3f}s")

        return final_context

    def _process_turn_legacy(self, query: str, turn_index: int) -> str:
        """旧版流程（回退，当 Turn 类不可用时）。"""
        enhanced_query = self._inject_user_profile(query)
        routed_mode = self._route_mode_legacy(enhanced_query, turn_index)
        if self.pipeline is None:
            return ""
        context = self.pipeline.process_turn(enhanced_query, turn_index=turn_index)
        self._extract_and_update_user_features_legacy(query, context, turn_index)
        return context

    def _route_mode_legacy(self, query: str, turn_index: int) -> Any:
        """旧版路由（回退）。"""
        if self.router is None:
            return ProcessingMode.RULE if ProcessingMode else "rule"
        intent_label = None
        if self.pipeline and hasattr(self.pipeline, 'manager'):
            latest = self.pipeline.manager.get_latest_block()
            if latest:
                intent_label = getattr(latest, 'intent_label', None)
        return self.router.decide(query, intent_label, turn_index)

    def _extract_and_update_user_features(self, turn: Any) -> None:
        """提取用户特征并更新画像（含一致性校验）。
        
        重构：
        1. 从 Turn.raw_query 提取单轮特征
        2. 一致性校验：对比历史行为 vs 自我描述
        3. 更新用户画像（采信行为而非声明）
        4. 贝叶斯特征推断
        """
        if self.user_extractor is None or self.user_manager is None or self.user_profile is None:
            return
        
        try:
            # 1. 单轮特征提取
            raw_query = getattr(turn, "raw_query", "")
            features = self.user_extractor.extract(raw_query)
            
            # 2. 一致性校验（跨轮行为 vs 自我描述）
            if features and self.consistency_checker is not None and len(self._turn_history) >= 3:
                recent_turns = self._turn_history[-5:]
                features = self.consistency_checker.validate(features, recent_turns)
                if features.get("consistency_checked", False):
                    notes = features.get("consistency_notes", [])
                    if notes:
                        logger.info(f"Consistency check: {notes}")
                turn.consistency_adjusted = True
            
            # 3. 更新用户画像（置信度阈值）
            if features and features.get("confidence", 0) >= 0.5:
                self.user_profile.update_from_dict(features)
                self.user_manager.save(self.user_profile)
                logger.debug(f"User profile updated: {features}")
                
                # 4. 贝叶斯特征推断
                if self.user_profile.threshold_profile is not None:
                    try:
                        from core.agent.coordinator.adaptive_threshold import ThresholdProfile
                        tp = ThresholdProfile.from_dict(self.user_profile.threshold_profile)
                        tp.record_features(features)
                        self.user_profile.threshold_profile = tp.to_dict()
                        self.user_manager.save(self.user_profile)
                    except ImportError:
                        pass
        except Exception as e:
            logger.warning(f"User feature extraction failed: {e}")
    def _extract_and_update_user_features_legacy(self, query: str, context: str, turn_index: int = 0):
        """旧版特征提取（回退）。"""
        if self.user_extractor is None or self.user_manager is None or self.user_profile is None:
            return
        try:
            features = self.user_extractor.extract(query)
            if features and features.get("confidence", 0) >= 0.5:
                self.user_profile.update_from_dict(features)
                self.user_manager.save(self.user_profile)
        except Exception as e:
            logger.warning(f"User feature extraction failed: {e}")

    def preload(self) -> bool:
        """预加载所有组件。"""
        if self.pipeline:
            self.pipeline.preload(blocking=True)
        return True

    def get_user_profile(self) -> Optional[Any]:
        """获取当前用户画像。"""
        return self.user_profile

    def get_tasks(self) -> List[Any]:
        """获取所有任务。"""
        if self.task_manager:
            return self.task_manager.get_all_tasks()
        return []

    def get_task_summary(self, task_id: str) -> str:
        """获取任务摘要。"""
        if self.task_manager:
            return self.task_manager.get_task_summary(task_id)
        return ""

    def get_stats(self) -> Dict[str, Any]:
        """获取运行统计。"""
        stats = {
            "turn_count": self.turn_count,
            "user_id": self.user_id,
            "mode": self.mode,
        }
        if self.router:
            stats["router"] = self.router.get_stats()
        if self.pipeline and hasattr(self.pipeline, 'manager'):
            stats["blocks"] = self.pipeline.manager.block_count
        if self.task_manager:
            stats["tasks"] = len(self.task_manager.get_all_tasks())
        if self.user_profile:
            stats["user"] = {
                "tech_level": self.user_profile.tech_level,
                "domains": self.user_profile.domains,
                "style": self.user_profile.style,
                "turn_count": self.user_profile.turn_count,
            }
        return stats

    def save_session(self, path: str):
        """保存会话到文件（增强版：触发 LLM 审查）。"""
        # 触发完整审查（持久化时核查）
        audit_result = self._audit_topic_tree(force=True)
        logger.info(f"Pre-save audit: {audit_result}")

        if _save_session and self.pipeline:
            _save_session(self.pipeline.manager, path)
            logger.info(f"Session saved to {path}")
        return audit_result

    def _maybe_trigger_background_audit(self):
        """检查是否需要触发后台审查（每 5 轮或空闲时）。"""
        total_turns = len(self._turn_history)
        last_audit = getattr(self, '_last_audit_turns', 0)
        if total_turns - last_audit >= 5:
            # 触发异步审查（不阻塞当前流程）
            import threading
            thread = threading.Thread(
                target=self._audit_topic_tree,
                kwargs={"force": False},
                daemon=True,
                name=f"audit-{total_turns}"
            )
            thread.start()
            logger.info(f"Background audit triggered at turn {total_turns}")

    def load_session(self, path: str):
        """从文件加载会话。"""
        if _load_session and self.pipeline:
            manager = _load_session(path)
            # 替换现有 manager
            self.pipeline.manager = manager
            logger.info(f"Session loaded from {path}")

    def reset(self):
        """重置所有状态。"""
        if self.pipeline:
            self.pipeline.reset()
        if self.task_manager:
            self.task_manager.reset()
        self.turn_count = 0

    # ── 内部方法 ──────────────────────────────────────────────────

    def _inject_user_profile(self, query: str) -> str:
        """将用户画像注入查询。"""
        if self.user_profile is None:
            return query
        return self.user_profile.inject_context(query)

    def _route_mode(self, turn: Any, turn_index: int) -> Any:
        """模式路由（支持自适应阈值 + 贝叶斯反馈记录）。
        
        重构：使用 Turn 对象而非污染后的字符串，从 turn.router_context 获取上下文。
        """
        if self.router is None:
            return ProcessingMode.RULE if ProcessingMode else "rule"
        
        # 获取意图标签
        intent_label = None
        if self.pipeline and hasattr(self.pipeline, "manager"):
            latest = self.pipeline.manager.get_latest_block()
            if latest:
                intent_label = getattr(latest, "intent_label", None)
        
        # 获取/创建自适应阈值画像
        threshold_profile = None
        if self.user_profile is not None:
            try:
                from core.agent.coordinator.adaptive_threshold import ThresholdProfile
                if self.user_profile.threshold_profile is not None:
                    threshold_profile = ThresholdProfile.from_dict(self.user_profile.threshold_profile)
                else:
                    threshold_profile = ThresholdProfile(user_id=self.user_id, use_bayesian=True)
                    self.user_profile.threshold_profile = threshold_profile.to_dict()
            except ImportError:
                pass
        
        # 计算复杂度分数（使用 Turn 的干净文本）
        raw_score = 0
        query = turn.raw_query if hasattr(turn, "raw_query") else str(turn)
        if self.router and self.router.evaluator:
            score = self.router.evaluator.evaluate(query, intent_label, turn_index, threshold_profile=threshold_profile)
            raw_score = score.raw_total if hasattr(score, "raw_total") else score.total
        
        # 路由决策
        mode = self.router.decide(
            query=query,
            intent_label=intent_label,
            history_length=turn_index,
            threshold_profile=threshold_profile,
        )
        
        # 记录路由反馈（更新贝叶斯后验）
        if threshold_profile is not None:
            mode_str = mode.value if hasattr(mode, "value") else str(mode)
            threshold_profile.record_feedback(
                original_score=raw_score,
                used_mode=mode_str,
                user_correction=False,
                user_satisfied=None,
            )
            # 保存回用户画像
            self.user_profile.threshold_profile = threshold_profile.to_dict()
            if self.user_manager:
                self.user_manager.save(self.user_profile)
        
        return mode
    
    def _record_turn_once(self, turn: Any, latest_block: Any) -> None:
        """每 Turn 只调用一次 record_turn（修复话题切换检测）。

        话题切换检测策略：
        1. 使用 Turn 首个话语块的意图（比最后一个更稳定）
        2. 关键词重叠检测：jieba 提取关键词，与上一轮比较重叠度
           重叠度 < 20% → 话题切换
        3. 只记录一次，避免话语块拆分导致 turn_count 膨胀
        """
        if self.user_profile is None or self.user_manager is None:
            return

        # 获取当前 Turn 的意图（使用首个话语块，更稳定）
        intent = "unknown"
        if turn.discourse_blocks and len(turn.discourse_blocks) > 0:
            first_block = turn.discourse_blocks[0]
            intent = getattr(first_block, 'intent_label', 'unknown') or 'unknown'
        else:
            intent = getattr(latest_block, 'intent_label', 'unknown') or 'unknown'

        # 检测纠错（从当前 Turn 的 raw_query）
        is_correction = False
        if self.user_extractor and hasattr(self.user_extractor, 'detect_correction'):
            raw_query = getattr(turn, 'raw_query', '')
            is_correction = self.user_extractor.detect_correction(raw_query)

        # 检测话题切换：优先使用 TopicTreeManagerV2（极致化话题图决策）
        is_switch = False
        prev_topic_id = 0
        
        if self._turn_history and len(self._turn_history) >= 1:
            prev_turn = self._turn_history[-1]
            prev_topic_id = getattr(prev_turn, 'topic_id', 0)

        if is_correction and self._turn_history:
            # 纠错查询：强制创建新话题（用户纠正之前的内容）
            is_switch = True
            self._current_topic_id += 1
            logger.info(f"Correction detected: T{turn.turn_index} -> new topic {self._current_topic_id}")
        elif self._topic_tree_v2_available and self._topic_tree_v2:
            # 使用 TopicTreeManagerV2 做极致化话题路由决策（参考，不直接控制 _topic_tree）
            try:
                decision = self._topic_tree_v2.route(
                    turn.raw_query,
                    turn.turn_index,
                    query_intent=intent,
                    extracted_entities=[],
                )
                logger.info(
                    f"TopicTreeV2 decision: T{turn.turn_index} action={decision.action} "
                    f"cohesion={decision.cohesion_score:.2f} confidence={decision.confidence:.2f}"
                )
                # 记录节点映射（供 dashboard 读取 V2 结构）
                current_node = self._topic_tree_v2.get_current_node()
                if current_node and current_node.id not in self._node_id_to_topic_id:
                    self._node_id_to_topic_id[current_node.id] = self._current_topic_id
            except Exception as e:
                logger.warning(f"TopicTreeV2 route failed: {e}")
            
            # 回退到旧的重叠度计算做实际话题分配
            if self._turn_history and len(self._turn_history) >= 1:
                prev_turn = self._turn_history[-1]
                prev_topic_id = getattr(prev_turn, 'topic_id', 0)
                curr_query = getattr(turn, 'raw_query', '')
                if curr_query:
                    # 1. 与上一轮比较
                    prev_query = getattr(prev_turn, 'raw_query', '')
                    overlap_with_prev = self._compute_topic_overlap(prev_query, curr_query, context="prev_turn") if prev_query else 0.0
                    
                    # 2. 与所有历史话题比较（回溯能力）
                    best_match_topic = None
                    best_overlap = 0.0
                    for tid, node in self._topic_tree.items():
                        topic_turns = node.get("turns", [])
                        if not topic_turns:
                            continue
                        rep_turn = topic_turns[-1]
                        rep_query = getattr(rep_turn, 'raw_query', '')
                        if rep_query and rep_query != curr_query:
                            overlap = self._compute_topic_overlap(rep_query, curr_query, context="history")
                            if overlap > best_overlap:
                                best_overlap = overlap
                                best_match_topic = tid
                    
                    # 决策：先检查回溯（>0.50），再检查继续（>0.45），否则切换
                    if best_match_topic is not None and best_match_topic != prev_topic_id and best_overlap > 0.50:
                        # 回到历史话题（明确关联）
                        self._current_topic_id = best_match_topic
                        is_switch = True
                        logger.info(f"Topic backtrack: T{turn.turn_index} -> topic {best_match_topic} (overlap={best_overlap:.2f})")
                    elif overlap_with_prev > 0.45:
                        is_switch = False
                    else:
                        is_switch = True
                        self._current_topic_id += 1
                        logger.info(f"Topic switch: overlap={overlap_with_prev:.2f} between T{prev_turn.turn_index} and T{turn.turn_index}, new_topic={self._current_topic_id}")
        else:
            # 回退到旧的重叠度计算（TopicTreeManagerV2 不可用）
            if self._turn_history and len(self._turn_history) >= 1:
                prev_turn = self._turn_history[-1]
                prev_topic_id = getattr(prev_turn, 'topic_id', 0)
                curr_query = getattr(turn, 'raw_query', '')
                if curr_query:
                    prev_query = getattr(prev_turn, 'raw_query', '')
                    overlap_with_prev = self._compute_topic_overlap(prev_query, curr_query, context="prev_turn") if prev_query else 0.0
                    if overlap_with_prev > 0.45:
                        is_switch = False
                    else:
                        is_switch = True
                        self._current_topic_id += 1
                        logger.info(f"Fallback switch: overlap={overlap_with_prev:.2f}, new_topic={self._current_topic_id}")

        # 分配 topic_id 到 Turn
        turn.topic_id = self._current_topic_id
        
        # 构建/更新话题树节点
        topic_id = turn.topic_id
        if topic_id not in self._topic_tree:
            # 新话题：推断名称
            topic_name = self._infer_topic_name(turn, is_switch)
            self._topic_tree[topic_id] = {
                "name": topic_name,
                "turns": [],
                "domains": set(),
                "intent": intent,
                "start_idx": turn.turn_index,
                "end_idx": turn.turn_index,
                "parent_topic": prev_topic_id if is_switch else None,
                # 三级存储：L2 语义摘要（非关键词，带解释）
                "semantic_summary": None,      # LLM 生成的语义摘要
                "summary_embedding": None,      # 摘要的 BGE 向量（用于搜索）
                "audit_status": "pending",      # 审查状态：pending/audited/corrected
                "audit_reason": None,           # 审查修正原因
            }
        
        # 更新话题节点
        node = self._topic_tree[topic_id]
        node["turns"].append(turn)
        node["end_idx"] = turn.turn_index
        
        # 聚合 domains（话题级别隔离，不污染用户画像）
        if hasattr(turn, 'raw_query') and turn.raw_query:
            extracted = self._extract_topic_keywords(turn.raw_query)
            node["domains"].update(extracted)
            
            # 更新用户画像时只保留当前话题的领域（不是全局累积）
            # 这样 Dashboard 显示的是当前话题的领域标签
            if self.user_profile:
                # 临时覆盖：用户画像只反映当前话题领域
                # 长期统计在后台审查时更新
                self.user_profile.domains = list(node["domains"])[:10]

        # 每 Turn 只调用一次
        self.user_manager.record_turn(
            self.user_id,
            intent=intent,
            is_correction=is_correction,
            is_switch=is_switch,
        )

        # ── P1: 自动持久化 ─────────────────────────────────────────
        self._persist_turn(turn, topic_id, intent, is_switch, is_correction)

        # 三级存储：触发后台审查（每 5 轮异步审查）
        self._maybe_trigger_background_audit()

    def _persist_turn(self, turn: Any, topic_id: int, intent: str, is_switch: bool, is_correction: bool) -> None:
        """自动持久化：轮次、话题、用户画像、向量 → SQLite。"""
        try:
            from core.infrastructure.sqlite_store import get_sqlite_store
            store = get_sqlite_store()

            # 1. 保存会话（确保存在）
            store.save_session(self.session_id, self.user_id)

            # 2. 保存轮次
            raw_query = getattr(turn, 'raw_query', '')
            router_mode = getattr(turn.metadata, 'router_mode', 'unknown') if hasattr(turn, 'metadata') else 'unknown'
            latency_ms = getattr(turn.metadata, 'latency_ms', 0.0) if hasattr(turn, 'metadata') else 0.0
            store.save_turn(
                self.session_id,
                turn.turn_index,
                raw_query,
                topic_id=topic_id,
                intent=intent,
                router_mode=router_mode,
                latency_ms=latency_ms,
            )

            # 3. 保存话题
            node = self._topic_tree.get(topic_id)
            if node:
                turn_indices = [t.turn_index for t in node.get("turns", [])]
                store.save_topic(
                    self.session_id,
                    topic_id,
                    name=node.get("name", f"话题 {topic_id}"),
                    turns=turn_indices,
                    domains=list(node.get("domains", set())),
                    intent=node.get("intent"),
                    start_idx=node.get("start_idx"),
                    end_idx=node.get("end_idx"),
                    parent_topic=node.get("parent_topic"),
                    semantic_summary=node.get("semantic_summary"),
                    audit_status=node.get("audit_status", "pending"),
                )

            # 4. 保存用户画像
            if self.user_profile:
                profile_dict = {
                    "tech_level": self.user_profile.tech_level,
                    "domains": self.user_profile.domains,
                    "style": self.user_profile.style,
                    "threshold_profile": self.user_profile.threshold_profile,
                    "turn_count": self.user_profile.turn_count,
                }
                store.save_user_profile(self.user_id, profile_dict)

            # 5. 保存语义向量（如果 semantic_index 有数据）
            if self.semantic_index:
                blocks = self.semantic_index.get_all_blocks()
                vectors = []
                for block_id, text, vec in blocks:
                    vectors.append((block_id, self.session_id, vec, text))
                if vectors:
                    store.save_vectors(self.session_id, vectors)

            logger.debug(f"Persisted turn {turn.turn_index} to SQLite")
        except Exception as e:
            logger.warning(f"Auto-persistence failed: {e}")

    def _restore_session(self) -> bool:
        """从 SQLite 恢复会话数据（轮次、话题树、用户画像、向量）。

        在 __init__ 中调用，实现重启后自动恢复。
        """
        try:
            from core.infrastructure.sqlite_store import get_sqlite_store
            store = get_sqlite_store()

            # 1. 检查会话是否存在
            session = store.load_session(self.session_id)
            if not session:
                logger.info(f"No previous session found for {self.session_id}")
                return False

            logger.info(f"Restoring session {self.session_id}...")

            # 2. 恢复用户画像
            profile = store.load_user_profile(self.user_id)
            if profile and self.user_profile:
                self.user_profile.tech_level = profile.get("tech_level")
                self.user_profile.domains = profile.get("domains", [])
                self.user_profile.style = profile.get("style")
                self.user_profile.threshold_profile = profile.get("threshold_profile")
                self.user_profile.turn_count = profile.get("turn_count", 0)
                logger.info(f"Restored user profile: {self.user_profile.tech_level}, domains={self.user_profile.domains}")

            # 3. 恢复话题树
            topics = store.load_topics(self.session_id)
            for t in topics:
                tid = t["topic_id"]
                self._topic_tree[tid] = {
                    "name": t.get("name", f"话题 {tid}"),
                    "turns": [],  # 将在恢复轮次后填充
                    "domains": set(t.get("domains", [])),
                    "intent": t.get("intent"),
                    "start_idx": t.get("start_idx"),
                    "end_idx": t.get("end_idx"),
                    "parent_topic": t.get("parent_topic"),
                    "semantic_summary": t.get("semantic_summary"),
                    "audit_status": t.get("audit_status", "pending"),
                    "summary_embedding": None,
                    "audit_reason": None,
                }
                self._current_topic_id = max(self._current_topic_id, tid)
            logger.info(f"Restored {len(topics)} topics")

            # 4. 恢复轮次（重建 _turn_history 和话题树中的 turns）
            turns = store.load_turns(self.session_id)
            restored_turns = 0
            for t in turns:
                # 创建简易 Turn 对象（不需要 full Turn 类，只需关键属性）
                class _RestoredTurn:
                    pass
                rt = _RestoredTurn()
                rt.turn_index = t["turn_index"]
                rt.raw_query = t["raw_query"]
                rt.topic_id = t["topic_id"]
                rt.discourse_blocks = []
                rt.context_blocks = []
                rt.metadata = type('obj', (object,), {
                    'router_mode': t.get("router_mode", "unknown"),
                    'latency_ms': t.get("latency_ms", 0.0),
                })()
                self._turn_history.append(rt)

                # 填充到话题树
                tid = t["topic_id"]
                if tid in self._topic_tree:
                    self._topic_tree[tid]["turns"].append(rt)

                restored_turns += 1
                self.turn_count = max(self.turn_count, rt.turn_index + 1)

            logger.info(f"Restored {restored_turns} turns, turn_count={self.turn_count}")

            # 5. 恢复语义向量
            if self.semantic_index:
                vectors = store.load_vectors(self.session_id)
                for v in vectors:
                    self.semantic_index._vectors[v["block_id"]] = v["vector"]
                    self.semantic_index._texts[v["block_id"]] = v["text"]
                    self.semantic_index._index_count += 1
                logger.info(f"Restored {len(vectors)} vectors")

            return True
        except Exception as e:
            logger.warning(f"Session restore failed: {e}")
            return False

    def _compute_topic_overlap(self, query1: str, query2: str, context: str = "default") -> float:
        """计算两个查询的话题重叠度（0-1）——三级协同架构。

        三级架构：
        1. Tier 1（实时层）：本地 BGE + 多信号融合快速判断
           - 明显同一话题（>0.65）或明显切换（<0.15）→ 直接返回，零 LLM 成本
        2. Tier 2（边界层）：LLM 语义仲裁
           - 模糊区 [0.15, 0.65] → 调用 LLM 判断话题关系
           - 返回 0-1 分数，覆盖本地判断
        3. Tier 3（修正层）：后台异步审查（_audit_topic_tree，已独立实现）

        记录：每次仲裁结果缓存，用于后续贝叶斯反馈优化阈值。
        """
        # Tier 1: 本地快速计算
        local_score = self._local_topic_overlap(query1, query2, context)

        # 快速路径：明确区
        if local_score > 0.65 or local_score < 0.15:
            logger.debug(f"Topic overlap fast path: {local_score:.2f} (local)")
            return local_score

        # Tier 2: 边界仲裁（模糊区）
        llm_score = self._llm_topic_arbitration(query1, query2, local_score, context)
        if llm_score is not None:
            logger.info(
                f"Topic overlap LLM arbitration: local={local_score:.2f} -> llm={llm_score:.2f}"
            )
            return llm_score

        # LLM 仲裁失败，回退到本地判断
        return local_score

    def _local_topic_overlap(self, query1: str, query2: str, context: str = "default") -> float:
        """本地话题重叠度计算（Tier 1）：语义主导 + 多信号融合 + 自适应校正。

        核心问题：BGE 在短句级别区分度不足（典型范围 0.60-0.90，难以区分同一话题 vs 切换）。
        解决方案：
        1. BGE 拉伸：将窄范围映射到宽范围，增强区分度
        2. 词汇差异惩罚：仅在长句中有效（短句词汇量天然少，Jaccard 不可靠）
        3. 语法连贯：主谓宾结构重叠（局部语义角色一致性）
        4. 话语关系标记：仅在模糊区提供辅助验证（低权重，不覆盖语义决策）

        设计理念：差异度驱动。不是看两个句子有多"像"，而是看它们有多"不同"。
        多维度差异度融合后，得到更可靠的话题边界判断。

        Args:
            context: "default"（通用）/ "prev_turn"（与上一轮比较）/ "history"（与历史话题回溯）
        """
        # 维度 1: 语义相似度（BGE）——需要拉伸，因为短句 BGE 范围窄
        raw_semantic = self._semantic_similarity(query1, query2)
        if raw_semantic is None:
            raw_semantic = 0.0

        # BGE 拉伸：将典型范围 0.60-0.90 映射到 0-1
        # 原理：BGE 在短句上的绝对值偏高但区分度不足，通过拉伸放大差异
        bge_min, bge_max = 0.60, 0.90
        if raw_semantic <= bge_min:
            semantic_score = 0.0
        elif raw_semantic >= bge_max:
            semantic_score = 1.0
        else:
            semantic_score = (raw_semantic - bge_min) / (bge_max - bge_min)

        # 维度 2: 关键词 Jaccard（词汇层面重叠）
        keyword_sim = self._keyword_jaccard(query1, query2)

        # 维度 3: 主谓宾语法连贯
        syntax_score = self._syntax_overlap(query1, query2)
        if syntax_score is None:
            syntax_score = 0.0

        # 维度 4: 话语关系检测（辅助，仅用于模糊区）
        relation = self._detect_discourse_relation(query1, query2)
        discourse_boost = 0.0

        if context in ("default", "prev_turn"):
            if relation == "progression":
                discourse_boost = 0.10
            elif relation == "causal":
                discourse_boost = 0.08
            elif relation == "contrast":
                discourse_boost = -0.20  # 转折显著降低相似度
            elif relation == "backtrack":
                if keyword_sim > 0.2:  # 有词汇关联 → 回溯成功
                    discourse_boost = 0.12
                else:
                    discourse_boost = -0.10  # 词汇不关联 → 假回溯

        # 句子长度：短句的 Jaccard 不可靠，长句的 Jaccard 更可靠
        avg_len = (len(query1) + len(query2)) / 2.0
        is_short = avg_len < 20  # 短句：<20 字
        is_long = avg_len > 40  # 长句：>40 字

        # 词汇差异惩罚：仅在长句中有效
        # 短句 Jaccard 天然低，不应惩罚；长句 Jaccard 低才说明话题不同
        lexical_penalty = 0.0
        if is_long:
            if keyword_sim < 0.05:
                lexical_penalty = 0.25
            elif keyword_sim < 0.15:
                lexical_penalty = 0.15
            elif keyword_sim < 0.30:
                lexical_penalty = 0.08
        elif not is_short:  # 中等长度
            if keyword_sim < 0.05:
                lexical_penalty = 0.15
            elif keyword_sim < 0.15:
                lexical_penalty = 0.08
        # 短句：不惩罚（Jaccard 不可靠）

        adjusted_semantic = max(0.0, semantic_score - lexical_penalty)

        # 自适应加权：根据句子长度调整权重
        # 短句：BGE 更可靠（语法/词汇在短句中不稳定），提高语义权重
        # 长句：词汇/语法更可靠，降低语义权重（BGE 在长句上可能更稳定但也可能有噪音）
        if is_short:
            # 短句：语义为主（BGE 在短句上虽范围窄但相对稳定），词汇为辅
            w_semantic = 0.55
            w_keyword = 0.20
            w_syntax = 0.20
            w_discourse = 0.05
        elif is_long:
            # 长句：词汇和语法更可靠
            w_semantic = 0.35
            w_keyword = 0.30
            w_syntax = 0.25
            w_discourse = 0.10
        else:
            # 中等长度：平衡
            w_semantic = 0.45
            w_keyword = 0.25
            w_syntax = 0.20
            w_discourse = 0.10

        base_score = (
            adjusted_semantic * w_semantic +
            keyword_sim * w_keyword +
            syntax_score * w_syntax
        )

        # 应用话语关系辅助
        final_score = base_score + discourse_boost * w_discourse

        # 语法连贯额外 boost：主谓宾高度一致 = 强话题延续信号
        if syntax_score >= 0.7:
            final_score = min(1.0, final_score + 0.08)

        # 关键词重叠额外 boost：短句中高 Jaccard = 强话题延续信号
        if is_short and keyword_sim > 0.5:
            final_score = min(1.0, final_score + 0.10)

        return max(0.0, min(1.0, final_score))

    def _llm_topic_arbitration(self, query1: str, query2: str, local_score: float, context: str) -> Optional[float]:
        """LLM 话题边界仲裁（Tier 2）：模糊区语义判断。

        触发条件：本地分数在 [0.15, 0.65] 模糊区
        职责：判断 query2 是 query1 的话题延续还是话题切换
        返回：0-1 分数（None = 仲裁失败，回退本地判断）

        设计原则：
        - 给 LLM 提供完整的上下文（两个查询 + 本地分数 + 各维度信号）
        - 要求 LLM 返回结构化判断（分数 + 理由）
        - 缓存结果，避免重复仲裁
        """
        # 检查缓存
        cache_key = (query1[:50], query2[:50], context)
        if hasattr(self, '_arbitration_cache'):
            if cache_key in self._arbitration_cache:
                return self._arbitration_cache[cache_key]
        else:
            self._arbitration_cache = {}

        # 构建 LLM 提示词
        # 收集各维度信号，供 LLM 参考（但不强制 LLM 跟随）
        raw_semantic = self._semantic_similarity(query1, query2) or 0.0
        keyword_sim = self._keyword_jaccard(query1, query2)
        syntax_score = self._syntax_overlap(query1, query2) or 0.0
        relation = self._detect_discourse_relation(query1, query2)

        prompt = f"""Judge whether the second query is a topic continuation or a topic switch from the first query.

Query 1: {query1}
Query 2: {query2}

Local signals (for reference only, not binding):
- Semantic similarity (BGE): {raw_semantic:.3f}
- Keyword overlap: {keyword_sim:.3f}
- Syntax coherence: {syntax_score:.3f}
- Discourse relation: {relation}
- Local combined score: {local_score:.3f}

Instructions:
1. Consider the semantic intent and topic domain of both queries
2. A query starting with "那/如果/然后" is usually continuation
3. A query starting with "对了/但是/不过" is often a switch or contrast
4. "回到刚才" indicates backtracking to a previous topic
5. Purely causal/hypothetical extensions ("如果...") within the same domain are continuation

Output ONLY a number from 0.0 to 1.0:
- 0.0-0.2: clear topic switch (different domains, unrelated content)
- 0.3-0.5: weak relation (same broad domain but different focus)
- 0.6-0.8: continuation (same topic, extending or elaborating)
- 0.9-1.0: strong continuation (direct follow-up, same subject)

Score:"""

        try:
            from core.agent.coordinator.multi_tier_llm_client import invoke_llm

            result = invoke_llm(
                prompt=prompt,
                task_type="topic_arbitration",  # 匹配 TASK_TIER_MAP 映射到 Tier 2
                system_prompt="You are a topic boundary detection expert. Output only a single number between 0.0 and 1.0. No explanation.",
                max_tokens=50,
                temperature=0.1,
            )

            if result:
                # 解析分数
                import re
                # 提取第一个数字
                match = re.search(r'(\d+\.?\d*)', result.strip().replace(',', ''))
                if match:
                    score = float(match.group(1))
                    score = max(0.0, min(1.0, score))
                    # 缓存
                    self._arbitration_cache[cache_key] = score
                    return score

        except Exception as e:
            logger.warning(f"LLM topic arbitration failed: {e}")

        return None

    def _semantic_similarity(self, query1: str, query2: str) -> Optional[float]:
        """使用 BGE 语义模型计算两个查询的余弦相似度（纯语义，无白名单）。"""
        try:
            if self.semantic_index is None:
                return None

            encoder = self.semantic_index._get_encoder()
            if encoder is None:
                return None

            import numpy as np
            vec1 = encoder.encode(query1)
            vec2 = encoder.encode(query2)

            if vec1 is None or vec2 is None or len(vec1) == 0 or len(vec2) == 0:
                return 0.0

            vec1 = np.squeeze(vec1)
            vec2 = np.squeeze(vec2)

            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = float(np.dot(vec1, vec2) / (norm1 * norm2))
            return similarity
        except Exception:
            return None

    def _syntax_overlap(self, query1: str, query2: str) -> Optional[float]:
        """主谓宾结构对应度（语法层面连贯性）。

        提取两个查询的主谓宾框架，比较：
        - 主语一致 → +0.35
        - 谓语一致 → +0.35
        - 宾语一致 → +0.30
        - 无主语但谓语一致 → +0.5（省略主语的延续）

        Returns: 0-1，None 如果无法提取
        """
        try:
            import jieba.posseg as pseg

            def extract_svo(text: str) -> Dict[str, str]:
                """提取主谓宾（简化版）。"""
                words = list(pseg.cut(text))
                subject = ""
                verb = ""
                obj = ""

                verb_idx = -1
                for i, (word, flag) in enumerate(words):
                    if flag.startswith('v') and len(word) >= 1 and word not in {"是", "有", "在", "想", "要"}:
                        verb = word
                        verb_idx = i
                        break
                    if word in {"想", "要", "打算", "准备"} and verb_idx < 0:
                        verb = word
                        verb_idx = i

                if verb_idx < 0:
                    nouns = [w for w, f in words if f.startswith('n') and len(w) >= 2]
                    return {"subject": "", "verb": "", "object": "".join(nouns[:2])}

                for i in range(verb_idx - 1, -1, -1):
                    word, flag = words[i]
                    if flag.startswith('r') or flag.startswith('n'):
                        subject = word
                        break

                obj_parts = []
                for i in range(verb_idx + 1, len(words)):
                    word, flag = words[i]
                    if flag.startswith('n') or flag == 'eng':
                        obj_parts.append(word)
                    if len(obj_parts) >= 2:
                        break
                obj = "".join(obj_parts)

                return {"subject": subject, "verb": verb, "object": obj}

            svo1 = extract_svo(query1)
            svo2 = extract_svo(query2)

            score = 0.0
            has_match = False

            if svo1["subject"] and svo2["subject"]:
                if svo1["subject"] == svo2["subject"]:
                    score += 0.35
                    has_match = True

            if svo1["verb"] and svo2["verb"]:
                if svo1["verb"] == svo2["verb"]:
                    score += 0.35
                    has_match = True
                elif svo1["verb"] in {"想", "要"} and svo2["verb"] in {"想", "要"}:
                    score += 0.30
                    has_match = True

            if svo1["object"] and svo2["object"]:
                if svo1["object"] == svo2["object"]:
                    score += 0.30
                    has_match = True
                elif svo1["object"] in svo2["object"] or svo2["object"] in svo1["object"]:
                    score += 0.20
                    has_match = True

            if not has_match:
                return 0.1

            return score
        except Exception as e:
            logger.debug(f"Syntax overlap failed: {e}")
            return None

    def _keyword_jaccard(self, query1: str, query2: str) -> float:
        """关键词 Jaccard 相似度（jieba 名词/动词/英文提取，无白名单）。"""
        try:
            import jieba.posseg as pseg

            words1 = set()
            words2 = set()

            for word, flag in pseg.cut(query1):
                if len(word) >= 2 and (flag.startswith('n') or flag.startswith('v') or flag == 'eng'):
                    words1.add(word.lower())

            for word, flag in pseg.cut(query2):
                if len(word) >= 2 and (flag.startswith('n') or flag.startswith('v') or flag == 'eng'):
                    words2.add(word.lower())

            if not words1 or not words2:
                return 0.0

            intersection = len(words1 & words2)
            union = len(words1 | words2)
            return intersection / union if union > 0 else 0.0
        except Exception:
            return 0.0

    def _detect_discourse_relation(self, query1: str, query2: str) -> str:
        """检测话语关系——基于语义推断 + 标记词辅助验证。

        设计理念：
        1. 首先计算语义向量关系（主导）
        2. 然后检查话语标记词（辅助验证）
        3. 两者冲突时，以语义推断为准

        话语关系类型：
        - progression: 语义延续（同一话题继续）
        - backtrack: 语义回溯（回到之前话题）
        - contrast: 语义转折（话题切换/否定）
        - causal: 因果/条件（同一话题的条件延伸）
        - none: 无明确关系（由语义相似度决定）
        """
        q2 = query2.strip()
        q1 = query1.strip()

        if not q1 or not q2:
            return "none"

        # 步骤 1: 语义推断（主导）
        semantic_sim = self._semantic_similarity(q1, q2) or 0.0

        # 语义相似度极高 -> 必然是延续
        if semantic_sim > 0.85:
            return "progression"

        # 语义相似度极低 -> 可能是切换
        if semantic_sim < 0.2:
            # 检查是否是回溯（语义有微弱联系）
            keyword_sim = self._keyword_jaccard(q1, q2)
            if keyword_sim > 0.3:
                return "backtrack"
            return "contrast"

        # 步骤 2: 话语标记词检测（辅助验证，仅用于语义模糊区 0.2-0.85）
        # 注意：标记词单独不做决定，只验证或微调语义推断

        # 检查 q2 开头的话语标记词
        # 使用前缀匹配（更精确），且要求标记词后有实际内容
        backtrack_markers = ["回到刚才", "继续之前", "刚才那个", "之前说的", "回到之前",
                             "继续刚才", "刚才提到", "之前提到", "刚才说的", "之前提到的"]
        for m in backtrack_markers:
            if q2.startswith(m) and len(q2) > len(m) + 2:
                return "backtrack"

        progression_markers = ["那", "然后", "还有", "接着", "接下来", "另外", "再者",
                               "除此之外", "顺便", "对了，那", "那么", "另外"]
        for m in progression_markers:
            if q2.startswith(m) and len(q2) > len(m) + 2:
                # 排除切换性质的短句
                if m == "对了" and len(q2) <= 6:
                    return "contrast"
                # 验证：语义不应该太低
                if semantic_sim > 0.15:
                    return "progression"
                break

        contrast_markers = ["但是", "不过", "然而", "可是", "却", "其实",
                            "不对", "错了", "不是", "没有", "否则"]
        for m in contrast_markers:
            if q2.startswith(m) and len(q2) > len(m) + 2:
                # 转折不一定是话题切换，可能只是观点转折
                # 如果语义相似度还比较高，可能是观点转折而非话题切换
                if semantic_sim > 0.5:
                    # 观点转折：继续同一话题
                    return "progression"
                return "contrast"

        causal_markers = ["因为", "所以", "由于", "因此", "既然",
                          "如果", "假如", "假设", "要是"]
        for m in causal_markers:
            if q2.startswith(m) and len(q2) > len(m) + 2:
                # 条件/因果通常是同一话题的延伸
                if semantic_sim > 0.15:
                    return "causal"
                break

        # 步骤 3: 无明确标记词时的语义推断
        if semantic_sim > 0.6:
            return "progression"
        elif semantic_sim > 0.35:
            return "none"  # 模糊区，由调用者根据阈值决定
        else:
            return "contrast"

    def _domain_coherence(self, query1: str, query2: str) -> float:
        """领域一致性检测——纯语义方法，无白名单。

        旧实现：使用 TECH_SUBDOMAINS 白名单（垂直领域思路，缺乏泛化能力）
        新实现：基于语义向量相似度推断领域一致性

        原理：同一领域的查询在语义空间中距离更近
        返回：
        - 1.0：语义推断为同一领域
        - 0.0：语义推断为不同领域
        - 0.5：不确定（语义模糊区）
        """
        # 纯语义方法：如果语义相似度足够高，认为是同一领域
        semantic_sim = self._semantic_similarity(query1, query2)
        if semantic_sim is None:
            return 0.5

        if semantic_sim > 0.6:
            return 1.0
        elif semantic_sim < 0.2:
            return 0.0
        else:
            # 模糊区：检查关键词重叠作为辅助
            keyword_sim = self._keyword_jaccard(query1, query2)
            if keyword_sim > 0.4:
                return 0.8
            elif keyword_sim < 0.1:
                return 0.2
            return 0.5

    def _tech_term_overlap(self, query1: str, query2: str) -> float:
        """技术术语重叠度——泛化版本，无领域白名单。

        提取所有英文词和中文专业词，计算 Jaccard 相似度。
        不再使用白名单过滤，而是让所有词参与统计。
        """
        import re

        # 提取英文词（大写开头或全大写缩写）
        tech1 = set(re.findall(r'[A-Za-z][a-zA-Z0-9]+', query1))
        tech2 = set(re.findall(r'[A-Za-z][a-zA-Z0-9]+', query2))

        # 过滤单字母和常见停用词（仅过滤最通用的英文功能词，不过滤领域词）
        stop_words = {
            'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'shall', 'can',
            'need', 'dare', 'ought', 'used', 'to', 'of', 'in', 'for',
            'on', 'at', 'by', 'with', 'from', 'as', 'into', 'through',
            'during', 'before', 'after', 'above', 'below', 'between',
            'under', 'again', 'further', 'then', 'once', 'here', 'there',
            'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each',
            'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
            'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
            'just', 'and', 'but', 'if', 'or', 'because', 'until', 'while',
            'what', 'which', 'who', 'whom', 'this', 'that', 'these',
            'those', 'am', 'it', 'its', 'itself', 'they', 'them',
            'their', 'theirs', 'themselves', 'you', 'your', 'yours',
            'yourself', 'yourselves', 'he', 'him', 'his', 'himself',
            'she', 'her', 'hers', 'herself', 'we', 'us', 'our', 'ours',
            'ourselves', 'i', 'me', 'my', 'mine', 'myself', 'one', 'ones'
        }

        tech1 = {w.lower() for w in tech1 if len(w) >= 2 and w.lower() not in stop_words}
        tech2 = {w.lower() for w in tech2 if len(w) >= 2 and w.lower() not in stop_words}

        if not tech1 or not tech2:
            return 0.0

        intersection = len(tech1 & tech2)
        union = len(tech1 | tech2)
        return intersection / union if union > 0 else 0.0

    def _extract_topic_keywords(self, query: str, top_k: int = 5) -> List[str]:
        """提取话题关键词——基于统计词频，无白名单。

        使用 jieba 词性标注，提取名词和动词，按频率排序。
        不再使用白名单过滤，而是让统计决定重要性。
        """
        try:
            import jieba.posseg as pseg

            # 统计词频
            word_freq = {}
            for word, flag in pseg.cut(query):
                # 保留：名词(n*)、动词(v*)、英文(eng)，长度>=2
                if len(word) >= 2 and (flag.startswith('n') or flag.startswith('v') or flag == 'eng'):
                    # 过滤通用疑问词（这些不是话题关键词）
                    if word in {'什么', '怎么', '为什么', '多少', '哪里', '时候', '问题',
                                '内容', '东西', '事情', '情况', '时候', '时候',
                                '怎么', '怎样', '如何', '为何', '哪些', '哪个'}:
                        continue
                    word_freq[word] = word_freq.get(word, 0) + 1

            # 按频率排序，取 top_k
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            return [w for w, _ in sorted_words[:top_k]]
        except Exception:
            return []

    def _infer_topic_name(self, turn: Any, is_switch: bool) -> str:
        """从 Turn 的查询推断话题名称——基于统计关键词 + 首句截断。

        不再使用白名单过滤，而是提取最频繁的名词/动词作为话题标识。
        """
        query = getattr(turn, 'raw_query', '')
        if not query:
            return f"话题 {self._current_topic_id}"

        # 提取统计关键词
        keywords = self._extract_topic_keywords(query, top_k=3)

        if keywords:
            return ' · '.join(keywords[:2])

        # 回退：首句截断（前 20 字）
        first_sentence = query.split('，')[0].split('。')[0].split('？')[0].split('！')[0]
        return first_sentence[:20] + ('...' if len(first_sentence) > 20 else '')

    def _process_with_small_model(self, query: str, turn_index: int) -> str:
        """小模型增强处理。

        当前实现：调用规则流程，但让小模型辅助生成 v3 摘要。
        """
        # 先走规则流程
        context = self.pipeline.process_turn(query, turn_index=turn_index)

        # 小模型增强：对需要 v3 摘要的块，用 LLM 生成高质量摘要
        if self.pipeline and hasattr(self.pipeline, 'manager'):
            for block in self.pipeline.manager.get_blocks():
                if hasattr(block, 'summary') and block.summary:
                    if block.summary.v3 is None and hasattr(block, 'turn_count') and block.turn_count > 5:
                        # 小模型生成 v3 摘要（预留）
                        pass

        return context

    def _assemble_context(self, turn: Any, context: str, turn_index: int) -> str:
        """组装最终上下文（重构：使用 Turn.rendered_text）。
        
        组装顺序：
        1. Turn 的 ContextBlock（用户画像、任务进展等）
        2. 话语块上下文
        """
        if turn is None or not hasattr(turn, "rendered_text"):
            return context
        
        # 组装：ContextBlock 文本 + 话语块上下文
        rendered = turn.rendered_text
        if context and rendered != context:
            # 如果话语块上下文不同于 Turn 渲染文本，拼接两者
            return f"{rendered}\n\n[话语上下文]\n{context}"
        return rendered
    def semantic_search(self, query: str, top_k: int = 5, min_score: float = 0.3, wave: bool = False) -> List[Tuple[str, float, str]]:
        """语义搜索历史话语块。

        支持两种模式：
        - 基础模式：纯余弦相似度 Top-k（快速）
        - 水波扩散模式：从锚点 block 向外扩散，考虑轮次距离衰减（发现上下文关联）

        Args:
            query: 搜索查询文本
            top_k: 返回结果数量
            min_score: 最小相似度阈值
            wave: 是否启用水波扩散（从锚点向外扩散到邻近轮次）

        Returns:
            [(block_id, similarity_score, text), ...]
        """
        if self.semantic_index is None:
            return []

        try:
            # 1. 基础搜索：获取锚点
            base_results = self.semantic_index.search(query, top_k=top_k * 3, min_score=min_score)
            if not wave or not base_results:
                return base_results[:top_k]
            
            # 2. 水波扩散：从锚点向外扩散到邻近轮次
            import math
            
            # 收集所有候选 block
            all_candidates = list(base_results)  # [(block_id, sim, text)]
            anchor_block_ids = {r[0] for r in base_results[:3]}  # 前 3 个作为锚点
            
            # 从 pipeline manager 获取所有 blocks
            all_blocks = []
            if self.pipeline and hasattr(self.pipeline, 'manager'):
                all_blocks = self.pipeline.manager.get_blocks()
            
            # 获取锚点的轮次范围
            anchor_turns = set()
            for bid in anchor_block_ids:
                for block in all_blocks:
                    if getattr(block, 'id', '') == bid:
                        anchor_turns.add(getattr(block, 'end_turn', getattr(block, 'start_turn', 0)))
                        break
            
            if anchor_turns:
                min_anchor_turn = min(anchor_turns)
                max_anchor_turn = max(anchor_turns)
                
                # 扩散到邻近轮次（±3 轮）的 blocks
                for block in all_blocks:
                    block_id = getattr(block, 'id', '')
                    if not block_id or block_id in anchor_block_ids:
                        continue
                    
                    block_turn = getattr(block, 'end_turn', getattr(block, 'start_turn', 0))
                    turn_distance = min(abs(block_turn - t) for t in anchor_turns) if anchor_turns else 999
                    
                    # 只扩散到邻近轮次（±3 轮）
                    if turn_distance <= 3:
                        # 计算衰减权重
                        decay = math.exp(-turn_distance / 2.0)
                        
                        # 计算语义相似度（用 block 文本搜索）
                        block_text = getattr(block, 'text', '') or getattr(block, 'raw_text', '')
                        if block_text and len(block_text) >= 2:
                            try:
                                block_sim_results = self.semantic_index.search(block_text, top_k=1, min_score=0.0)
                                if block_sim_results:
                                    block_sim = block_sim_results[0][1]
                                    # 水波权重 = 语义相似度 * 轮次衰减
                                    weight = block_sim * decay
                                    if weight > min_score * 0.5:  # 扩散阈值更宽松
                                        all_candidates.append((block_id, weight, block_text))
                            except Exception:
                                pass
            
            # 去重并按权重排序
            seen = set()
            unique_results = []
            for bid, weight, text in sorted(all_candidates, key=lambda x: x[1], reverse=True):
                if bid not in seen and weight >= min_score:
                    seen.add(bid)
                    unique_results.append((bid, weight, text))
            
            logger.info(f"Wave search: {len(base_results)} anchors -> {len(unique_results)} results (wave_expanded={len(unique_results) - len(base_results)})")
            return unique_results[:top_k]
            
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")
            # 失败时回退到基础搜索
            try:
                return self.semantic_index.search(query, top_k=top_k, min_score=min_score)
            except Exception:
                return []

    def get_block_by_id(self, block_id: str) -> Optional[Any]:
        """通过 ID 获取话语块（跨会话全局查找）。

        查找顺序：
        1. 当前会话的 manager
        2. 跨会话全局索引
        """
        # 1. 当前会话
        if self.pipeline and hasattr(self.pipeline, 'manager'):
            block = self.pipeline.manager.get_block_by_id(block_id)
            if block:
                return block

        # 2. 跨会话全局索引
        return self._global_block_index.get(block_id)

    def index_session_blocks(self) -> int:
        """将当前会话的所有块添加到语义索引。

        Returns:
            成功索引的块数量
        """
        if self.semantic_index is None or self.pipeline is None:
            return 0

        if not hasattr(self.pipeline, 'manager'):
            return 0

        count = 0
        for block in self.pipeline.manager.get_blocks():
            block_id = getattr(block, 'id', None)
            text = getattr(block, 'raw_text', None)
            if block_id and text:
                if self.semantic_index.add_block(block_id, text):
                    count += 1
                    self._global_block_index[block_id] = block
        return count

    # ── Phase 3: 跨会话引用 ───────────────────────────────────────

    def load_session(self, path: str):
        """从文件加载会话（跨会话引用支持）。

        加载后会将所有块添加到全局索引和语义索引。
        """
        if _load_session and self.pipeline:
            manager = _load_session(path)
            self.pipeline.manager = manager

            loaded_count = 0
            for block in manager.get_blocks():
                block_id = getattr(block, 'id', None)
                text = getattr(block, 'raw_text', None)
                if block_id and text:
                    self._global_block_index[block_id] = block
                    if self.semantic_index and self.semantic_index.add_block(block_id, text):
                        loaded_count += 1

            logger.info(f"Session loaded from {path}, indexed {loaded_count} blocks")
        else:
            logger.warning(f"Session loading not available")

    # ── LLM 协同：语义摘要 + 异步审查 ──────────────────────────────

    def _generate_semantic_summary(self, topic_id: int) -> Optional[str]:
        """为话题生成 LLM 语义摘要（二级摘要，非关键词，带解释）。

        摘要示例：
        - 旧关键词：["Python", "推导式", "Flask", "API"]
        - 新语义摘要："用户在学 Python 编程，从列表推导式入门到字典推导式，
          后转向 Flask Web 框架的 REST API 设计，涉及用户注册和 JWT 验证"

        返回：语义摘要字符串，失败返回 None（不影响实时流程）
        """
        node = self._topic_tree.get(topic_id)
        if not node or not node["turns"]:
            return None

        # 获取话题的所有查询（用户输入）
        queries = []
        for turn in node["turns"]:
            raw = getattr(turn, 'raw_query', '')
            if raw:
                queries.append(raw)
        if not queries:
            return None

        # 英文 prompt（减少 reasoning tokens）
        queries_text = "\n".join(f"{i+1}. {q[:80]}" for i, q in enumerate(queries))
        prompt = f"""Summarize these user queries in ONE Chinese sentence (max 50 chars, include tech names like Python/Flask):

{queries_text}

Summary:"""

        # 调用多层 LLM（Tier 2: semantic_summary 路由到高端模型）
        try:
            from core.agent.coordinator.multi_tier_llm_client import invoke_llm

            # Tier 2 使用更详细的提示词（允许更长、更详细）
            result = invoke_llm(
                prompt=prompt,
                task_type="semantic_summary",
                system_prompt="Output Chinese summary directly. No explanation.",
                max_tokens=500,
                temperature=0.1,
            )
            if result and len(result) > 3:
                logger.info(f"Topic {topic_id} summary: {result[:60]}...")
                return result
        except Exception as e:
            logger.warning(f"Multi-tier LLM summary failed: {e}")

        return None

    def _update_topic_summary(self, topic_id: int) -> bool:
        """更新话题的语义摘要和摘要向量（带重试）。"""
        node = self._topic_tree.get(topic_id)
        if not node:
            return False

        # 生成摘要（最多重试 2 次）
        summary = None
        for attempt in range(2):
            summary = self._generate_semantic_summary(topic_id)
            if summary:
                break
            logger.warning(f"Summary generation for topic {topic_id} failed (attempt {attempt+1}), retrying...")
            import time
            time.sleep(0.5)

        if not summary:
            logger.error(f"Failed to generate summary for topic {topic_id} after 2 attempts")
            return False

        node["semantic_summary"] = summary

        # 计算摘要的 BGE 向量（用于搜索）
        if self.semantic_index:
            try:
                from core.agent.context_manager.semantic_index import np
                encoder = self.semantic_index._get_encoder()
                if encoder:
                    vec = encoder.encode(summary)
                    if vec is not None and len(vec) > 0:
                        vec = np.squeeze(vec)
                        norm = np.linalg.norm(vec)
                        if norm > 0:
                            vec = vec / norm
                        node["summary_embedding"] = vec.tolist()
                        return True
            except Exception as e:
                logger.warning(f"Summary embedding failed: {e}")

        return True  # 摘要生成了，但向量计算失败

    def _audit_topic_tree(self, force: bool = False) -> Dict[str, Any]:
        """LLM 完整审查话题树（持久化时/后台触发）。

        审查内容：
        1. 错误聚合检测：A 话题中混入明显不相关的 B 话题内容
        2. 话题拆分建议：一个话题内包含多个独立子话题
        3. 语义摘要生成/修正
        4. 话题关系重构（parent_topic 修正）

        Args:
            force: 是否强制审查（忽略 pending 状态）

        Returns:
            {"corrected": int, "splits": int, "summaries": int, "errors": List[str]}
        """
        if not self._topic_tree:
            return {"corrected": 0, "splits": 0, "summaries": 0, "errors": []}

        # 检查是否需要审查（每 5 轮或强制）
        total_turns = sum(len(n["turns"]) for n in self._topic_tree.values())
        last_audit = getattr(self, '_last_audit_turns', 0)
        if not force and total_turns - last_audit < 5:
            return {"corrected": 0, "splits": 0, "summaries": 0, "errors": ["Too early"], "skipped": True}

        self._last_audit_turns = total_turns

        result = {"corrected": 0, "splits": 0, "summaries": 0, "errors": []}

        # 1. 为所有 pending 话题生成语义摘要
        for tid, node in self._topic_tree.items():
            if node.get("audit_status") in ("pending", None) or node.get("semantic_summary") is None:
                if self._update_topic_summary(tid):
                    result["summaries"] += 1
                    node["audit_status"] = "audited"

        # 2. LLM 审查：检测错误聚合（可选，后台不阻塞）
        try:
            from core.agent.coordinator import get_small_model_client
            client = get_small_model_client()
            if client and client.is_available:
                corrections = self._llm_audit_topics(client)
                result["corrected"] = corrections.get("corrected", 0)
                result["splits"] = corrections.get("splits", 0)
        except Exception as e:
            result["errors"].append(str(e))
            logger.warning(f"LLM audit failed: {e}")

        logger.info(f"Topic tree audit: {result}")
        return result

    def _llm_audit_topics(self, client) -> Dict[str, int]:
        """LLM 批量审查话题树，返回修正计数。"""
        # 构建话题描述
        topics_desc = []
        for tid, node in sorted(self._topic_tree.items()):
            queries = [getattr(t, 'raw_query', '')[:80] for t in node["turns"]]
            summary = node.get("semantic_summary", "未生成")
            topics_desc.append(
                f"话题 {tid}: {node['name']}\n"
                f"  摘要: {summary}\n"
                f"  对话: {queries}"
            )

        if not topics_desc:
            return {"corrected": 0, "splits": 0}

        prompt = f"""请审查以下话题树，检测错误聚合和拆分机会。

【话题树】
{chr(10).join(topics_desc)}

【任务】
1. 检测是否有明显不相关的对话被聚合到同一话题
2. 检测是否有话题包含多个独立子话题需要拆分
3. 修正话题的 parent_topic 关系（如果存在逻辑从属）

【输出格式】
仅输出 JSON：
```json
{{
    "issues": [
        {{
            "topic_id": 数字,
            "issue_type": "misaggregation" | "oversized" | "wrong_parent",
            "description": "问题描述",
            "suggested_action": "建议操作"
        }}
    ],
    "corrections": 数字,
    "splits": 数字
}}
```"""

        # 调用多层 LLM（Tier 2: topic_audit 路由到高端模型，使用更详细的提示词）
        try:
            from core.agent.coordinator.multi_tier_llm_client import invoke_llm

            result = invoke_llm(
                prompt=prompt,
                task_type="topic_audit",
                system_prompt="You are a topic tree audit expert. Analyze topic tree quality.",
                max_tokens=400,
                temperature=0.1,
                parse_json=True,
            )
            if not result:
                return {"corrected": 0, "splits": 0}

            # 尝试解析 JSON
            try:
                import json
                json_start = result.find("{")
                json_end = result.rfind("}")
                if json_start >= 0 and json_end > json_start:
                    data = json.loads(result[json_start:json_end + 1])
                    return {
                        "corrected": data.get("corrections", 0),
                        "splits": data.get("splits", 0)
                    }
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"Multi-tier LLM audit failed: {e}")

        return {"corrected": 0, "splits": 0}

    def search_by_summary(self, query: str, top_k: int = 3) -> List[Tuple[int, float, str]]:
        """基于语义摘要的话题搜索（L2 温缓存优化）。

        搜索路径：
        1. 先匹配话题的语义摘要（向量相似度）
        2. 再深入匹配话题内的具体轮次
        3. 返回 (topic_id, score, summary) 列表

        这比直接搜索原始对话快得多（摘要数量 << 轮次数量）。
        """
        if not self._topic_tree:
            return []

        results = []

        # 1. 如果有 BGE 向量，用向量搜索摘要
        if self.semantic_index:
            try:
                query_vec = self.semantic_index._get_encoder()
                if query_vec:
                    import numpy as np
                    qv = query_vec.encode(query)
                    if qv is not None and len(qv) > 0:
                        qv = np.squeeze(qv)
                        q_norm = np.linalg.norm(qv)
                        if q_norm > 0:
                            qv = qv / q_norm

                        for tid, node in self._topic_tree.items():
                            emb = node.get("summary_embedding")
                            if emb:
                                emb = np.array(emb)
                                score = float(np.dot(qv, emb))
                                summary = node.get("semantic_summary", node.get("name", ""))
                                if score > 0.3:
                                    results.append((tid, score, summary))
            except Exception as e:
                logger.warning(f"Summary vector search failed: {e}")

        # 2. 回退：关键词匹配摘要文本
        if not results:
            query_words = set(query.lower().split())
            for tid, node in self._topic_tree.items():
                summary = node.get("semantic_summary", "")
                if summary:
                    summary_words = set(summary.lower().split())
                    overlap = len(query_words & summary_words) / max(len(query_words), 1)
                    if overlap > 0.2:
                        results.append((tid, overlap, summary))
                # 回退到 name
                elif node.get("name"):
                    name_words = set(node["name"].lower().split())
                    overlap = len(query_words & name_words) / max(len(query_words), 1)
                    if overlap > 0.3:
                        results.append((tid, overlap, node["name"]))

        # 排序并返回 top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def save_session_with_audit(self, path: str) -> Dict[str, Any]:
        """保存会话并触发 LLM 审查（持久化时完整核查）。

        这是 save_session 的增强版，在保存前：
        1. 为所有 pending 话题生成语义摘要
        2. 触发 LLM 完整审查（修正错误聚合）
        3. 保存审查后的状态
        """
        logger.info("Saving session with LLM audit...")

        # 1. 触发审查（后台，不阻塞保存）
        audit_result = self._audit_topic_tree(force=True)

        # 2. 保存会话（原始逻辑）
        if _save_session and self.pipeline:
            _save_session(self.pipeline.manager, path)
            logger.info(f"Session saved to {path}")

        # 3. 返回审查结果
        return {
            "saved": True,
            "path": path,
            "audit": audit_result,
            "topic_count": len(self._topic_tree),
            "summaries": sum(1 for n in self._topic_tree.values() if n.get("semantic_summary")),
        }
