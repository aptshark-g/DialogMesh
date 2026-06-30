# core/agent/user_engine/user_manager.py
"""用户管理器 —— 用户身份识别、跨会话聚合、持久化。

Phase 2 改进：
- 跨会话自动加载：用户画像在会话切换时自动从数据库加载
- 增量统计更新：每轮对话后自动更新 turn_count, topic_switches, correction_count
- 意图连续性追踪：记录 last_intent 和 consecutive_same_intent
- 派生指标计算：自动计算 topic_switch_rate, correction_rate

职责：
- user_id ↔ session_id 映射（一个用户可有多会话）
- 用户画像的持久化（SQLite 或 JSON）
- 会话切换时自动加载用户历史画像
- 增量更新：每次对话更新用户画像，不丢失历史

使用方式：
    manager = UserManager()
    user = manager.get_or_create(user_id="user_123")
    user.update_from_dict({"tech_level": "beginner", "domains": ["Python"]})
    manager.save(user)

    # 跨会话自动加载
    manager.bind_session("session_456", "user_123")
    user2 = manager.load_by_session("session_456")
    # → 自动加载 user_123 的历史画像
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent.user_engine.user_profile import UserProfile

logger = logging.getLogger(__name__)


class UserManager:
    """用户管理器 —— 支持跨会话自动加载与增量统计。"""

    DEFAULT_DB_PATH = Path.home() / ".config" / "memorygraph" / "users.db"

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or self.DEFAULT_DB_PATH
        self._cache: Dict[str, UserProfile] = {}  # user_id → UserProfile
        self._session_map: Dict[str, str] = {}    # session_id → user_id

        self._init_db()

    def _init_db(self):
        """初始化 SQLite 数据库。"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    profile_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.commit()

    def get_or_create(self, user_id: Optional[str] = None) -> UserProfile:
        """获取或创建用户画像。"""
        user_id = user_id or "anonymous"

        # 1. 检查缓存
        if user_id in self._cache:
            return self._cache[user_id]

        # 2. 从数据库加载
        profile = self._load_from_db(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            self._save_to_db(profile)

        self._cache[user_id] = profile
        return profile

    def load_by_session(self, session_id: str) -> Optional[UserProfile]:
        """通过会话 ID 自动加载用户画像（跨会话恢复）。

        流程：
        1. 检查 session_id 是否绑定到 user_id
        2. 从数据库加载该用户的画像
        3. 更新缓存

        Returns:
            用户画像（或 None，如果会话未绑定）
        """
        # 1. 检查 session 绑定
        user_id = self._session_map.get(session_id)
        if not user_id:
            # 从数据库查询
            try:
                with sqlite3.connect(str(self.db_path)) as conn:
                    row = conn.execute(
                        "SELECT user_id FROM sessions WHERE session_id = ?", (session_id,)
                    ).fetchone()
                    if row:
                        user_id = row[0]
                        self._session_map[session_id] = user_id
            except Exception as e:
                logger.warning(f"Failed to load session {session_id}: {e}")
                return None

        if not user_id:
            return None

        # 2. 从数据库加载用户画像
        profile = self._load_from_db(user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            self._save_to_db(profile)

        self._cache[user_id] = profile
        logger.info(f"User profile loaded for session {session_id}: {user_id}")
        return profile

    def bind_session(self, session_id: str, user_id: str):
        """绑定会话到用户。"""
        self._session_map[session_id] = user_id
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (session_id, user_id, created_at) VALUES (?, ?, ?)",
                (session_id, user_id, time.time()),
            )
            conn.commit()
        logger.debug(f"Session {session_id} bound to user {user_id}")

    def update_profile(self, user_id: str, data: Dict[str, Any]):
        """增量更新用户画像。"""
        profile = self.get_or_create(user_id)
        profile.update_from_dict(data)
        self._save_to_db(profile)
        self._cache[user_id] = profile

    def record_turn(self, user_id: str, intent: str = "unknown", is_correction: bool = False, is_switch: bool = False):
        """记录一轮交互统计（自动更新画像）。"""
        profile = self.get_or_create(user_id)
        profile.record_turn(intent=intent, is_correction=is_correction, is_switch=is_switch)
        self._save_to_db(profile)
        self._cache[user_id] = profile

    def save(self, profile: UserProfile):
        """保存用户画像。"""
        self._save_to_db(profile)
        self._cache[profile.user_id] = profile

    def _load_from_db(self, user_id: str) -> Optional[UserProfile]:
        """从数据库加载用户画像。"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT profile_json FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                if row:
                    data = json.loads(row[0])
                    return UserProfile.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load user {user_id} from DB: {e}")
        return None

    def _save_to_db(self, profile: UserProfile):
        """保存用户画像到数据库。"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO users (user_id, profile_json, updated_at) VALUES (?, ?, ?)",
                    (profile.user_id, json.dumps(profile.to_dict(), ensure_ascii=False), time.time()),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to save user {profile.user_id}: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。"""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                return {
                    "users": user_count,
                    "sessions": session_count,
                    "cached": len(self._cache),
                }
        except Exception:
            return {"users": 0, "sessions": 0, "cached": len(self._cache)}
