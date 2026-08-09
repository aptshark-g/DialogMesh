# -*- coding: utf-8 -*-
"""
service/api/__init__.py
───────────────────────
DialogMesh FastAPI 应用层公共导出。
"""

from __future__ import annotations

from service.api.main import create_app

__all__ = ["create_app"]
