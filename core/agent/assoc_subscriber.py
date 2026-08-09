# -*- coding: utf-8 -*-
"""Association Subscriber — 薄门面（一内核两门面，红线 7）。

内核: :class:`core.agent.association.association_service.AssociationService`
（M→1 定向通道 + EventLog Event Sourcing，蓝图 §7.3）。
此处保留旧类名/旧构造签名，供 CLI registry 与外部引用兼容。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.agent.association.association_service import (
    AssociationService,
    AssociationState,
    INTERESTED_KINDS,
)

logger = logging.getLogger(__name__)


class AssociationSubscriber(AssociationService):
    """兼容门面: 旧 ``AssociationSubscriber`` 名称指向独立服务内核。"""

    def __init__(self, event_log: Any = None, bus: Any = None,
                 llm_provider: Any = None, **kwargs):
        super().__init__(
            event_log=event_log,
            bus=bus,
            llm_provider=llm_provider,
            db_path=kwargs.pop("db_path", "data/event_log.db"),
            queue_size=kwargs.pop("queue_size", AssociationService.DEFAULT_QUEUE_SIZE),
        )


__all__ = ["AssociationSubscriber", "AssociationService", "AssociationState",
           "INTERESTED_KINDS"]
