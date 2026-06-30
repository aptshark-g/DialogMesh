# -*- coding: utf-8 -*-
"""
core/agent/frontend/clarification_ui.py
──────────────────────────────────────
Clarification UI 渲染协议（Layer 3，v2.4 新增）。

定义前端如何渲染澄清界面（按钮、选择器、输入框等）。
设计原则：
  - 只定义"什么信息 + 什么交互类型"，不定义具体 CSS
  - 渐进增强：基础实现只需支持文本 + 按钮，高级实现支持更多组件
  - 向后兼容：新增 UI 类型时，旧前端忽略未知类型，降级为文本显示
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# 基础数据模型
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class UIOption:
    """选项定义。"""
    value: str                              # 提交给服务端时的值
    display_text: str                       # 前端展示文案
    description: Optional[str] = None       # 悬停提示/副标题
    icon: Optional[str] = None              # 图标标识（前端映射到具体图标）
    highlighted: bool = False                # 是否高亮（推荐选项）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "display_text": self.display_text,
            "description": self.description,
            "icon": self.icon,
            "highlighted": self.highlighted,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> UIOption:
        return cls(
            value=d.get("value", ""),
            display_text=d.get("display_text", ""),
            description=d.get("description"),
            icon=d.get("icon"),
            highlighted=d.get("highlighted", False),
        )


@dataclass
class UIValidation:
    """输入校验规则。"""
    type: str                              # "regex" | "range" | "enum" | "required"
    pattern: Optional[str] = None          # regex 模式
    min: Optional[float] = None            # 数值最小值
    max: Optional[float] = None            # 数值最大值
    error_message: str = "输入无效，请重新填写"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "pattern": self.pattern,
            "min": self.min,
            "max": self.max,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> UIValidation:
        return cls(
            type=d.get("type", "required"),
            pattern=d.get("pattern"),
            min=d.get("min"),
            max=d.get("max"),
            error_message=d.get("error_message", "输入无效，请重新填写"),
        )


@dataclass
class UIComponent:
    """单个 UI 组件定义。"""
    type: str                              # 组件类型
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    label: Optional[str] = None            # 组件标签/标题
    options: List[UIOption] = field(default_factory=list)  # 选择型组件的选项
    placeholder: Optional[str] = None    # 输入型组件的占位符
    default_value: Optional[str] = None    # 默认值
    validation: Optional[UIValidation] = None  # 输入校验规则

    # 以下类型（见设计文档 §13.2.2）：
    # single_select, multi_select, text_input, number_input, address_input,
    # confirm_dangerous, show_info, progress_indicator, taskgraph_preview

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "type": self.type,
            "id": self.id,
            "label": self.label,
        }
        if self.options:
            result["options"] = [o.to_dict() for o in self.options]
        if self.placeholder is not None:
            result["placeholder"] = self.placeholder
        if self.default_value is not None:
            result["default_value"] = self.default_value
        if self.validation is not None:
            result["validation"] = self.validation.to_dict()
        return result

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> UIComponent:
        return cls(
            type=d.get("type", ""),
            id=d.get("id", str(uuid.uuid4())[:8]),
            label=d.get("label"),
            options=[UIOption.from_dict(o) for o in d.get("options", [])],
            placeholder=d.get("placeholder"),
            default_value=d.get("default_value"),
            validation=UIValidation.from_dict(d["validation"]) if "validation" in d else None,
        )


@dataclass
class ClarificationUISchema:
    """Clarification 前端渲染协议。"""
    version: str = "1.0"
    message_style: str = "default"          # "default" | "warning" | "info" | "tutorial"
    components: List[UIComponent] = field(default_factory=list)
    allow_free_text: bool = True            # 是否允许自由文本回复
    allow_skip: bool = False                # 是否允许跳过此澄清
    timeout_hint: str = "60秒内回复"          # 超时提示文案

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "message_style": self.message_style,
            "components": [c.to_dict() for c in self.components],
            "allow_free_text": self.allow_free_text,
            "allow_skip": self.allow_skip,
            "timeout_hint": self.timeout_hint,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ClarificationUISchema:
        return cls(
            version=d.get("version", "1.0"),
            message_style=d.get("message_style", "default"),
            components=[UIComponent.from_dict(c) for c in d.get("components", [])],
            allow_free_text=d.get("allow_free_text", True),
            allow_skip=d.get("allow_skip", False),
            timeout_hint=d.get("timeout_hint", "60秒内回复"),
        )

    def to_clarification_payload(self, message: str, clarification_id: str) -> Dict[str, Any]:
        """转换为与服务层兼容的 ClarificationPayload 字典。"""
        from core.agent.service.models import ClarificationPayload
        return {
            "clarification_id": clarification_id,
            "message": message,
            "suggestions": [o.display_text for c in self.components for o in c.options],
        }


# ──────────────────────────────────────────────────────────────────────────────
# 工厂方法：从歧义列表生成 Clarification UI
# ──────────────────────────────────────────────────────────────────────────────

class ClarificationUIFactory:
    """从歧义类型生成标准 Clarification UI 的工厂。"""

    # 样式映射
    STYLE_MAP = {
        "ambiguous_process": "info",
        "ambiguous_address": "warning",
        "missing_value": "info",
        "destructive_action": "warning",
        "unknown_intent": "info",
    }

    @classmethod
    def create_process_selector(
        cls,
        candidates: List[str],
        recommended_idx: int = 0,
    ) -> ClarificationUISchema:
        """创建进程选择器。"""
        options = []
        for i, candidate in enumerate(candidates):
            options.append(UIOption(
                value=candidate,
                display_text=candidate,
                highlighted=(i == recommended_idx),
            ))
        return ClarificationUISchema(
            message_style="info",
            components=[
                UIComponent(
                    type="show_info",
                    id="info-1",
                    label="检测到多个可能的进程，请选择目标进程：",
                ),
                UIComponent(
                    type="single_select",
                    id="process-select",
                    label="目标进程",
                    options=options,
                ),
                UIComponent(
                    type="text_input",
                    id="custom-pid",
                    label="或手动输入 PID",
                    placeholder="例如：1234",
                    validation=UIValidation(
                        type="regex",
                        pattern=r"^\d+$",
                        error_message="请输入数字",
                    ),
                ),
            ],
            allow_free_text=False,
            allow_skip=False,
            timeout_hint="60秒内选择进程",
        )

    @classmethod
    def create_address_selector(
        cls,
        addresses: List[str],
        recommended_idx: int = 0,
    ) -> ClarificationUISchema:
        """创建地址选择器。"""
        options = []
        for i, addr in enumerate(addresses):
            options.append(UIOption(
                value=addr,
                display_text=addr,
                highlighted=(i == recommended_idx),
            ))
        return ClarificationUISchema(
            message_style="warning",
            components=[
                UIComponent(
                    type="show_info",
                    id="addr-info",
                    label="发现多个匹配地址，请选择：",
                ),
                UIComponent(
                    type="multi_select",
                    id="address-select",
                    label="目标地址",
                    options=options,
                ),
                UIComponent(
                    type="address_input",
                    id="custom-address",
                    label="或输入新地址",
                    placeholder="例如：0x7FF6...",
                    validation=UIValidation(
                        type="regex",
                        pattern=r"^0x[0-9A-Fa-f]+$",
                        error_message="请输入有效的 0x 前缀地址",
                    ),
                ),
            ],
            allow_free_text=False,
            allow_skip=False,
            timeout_hint="60秒内选择地址",
        )

    @classmethod
    def create_value_input(
        cls,
        field_name: str,
        expected_type: str = "text",
        default: Optional[str] = None,
    ) -> ClarificationUISchema:
        """创建数值输入组件。"""
        comp_type = "number_input" if expected_type == "number" else "text_input"
        validation = None
        if expected_type == "number":
            validation = UIValidation(type="range", min=0, max=999999999, error_message="请输入有效数值")
        elif expected_type == "address":
            comp_type = "address_input"
            validation = UIValidation(type="regex", pattern=r"^0x[0-9A-Fa-f]+$", error_message="请输入有效的 0x 前缀地址")

        return ClarificationUISchema(
            message_style="info",
            components=[
                UIComponent(
                    type="show_info",
                    id="input-info",
                    label=f"需要补充信息：{field_name}",
                ),
                UIComponent(
                    type=comp_type,
                    id="value-input",
                    label=field_name,
                    placeholder=f"请输入{field_name}",
                    default_value=default,
                    validation=validation,
                ),
            ],
            allow_free_text=True,
            allow_skip=False,
            timeout_hint="60秒内补充信息",
        )

    @classmethod
    def create_dangerous_confirm(
        cls,
        action_description: str,
    ) -> ClarificationUISchema:
        """创建危险操作确认。"""
        return ClarificationUISchema(
            message_style="warning",
            components=[
                UIComponent(
                    type="show_info",
                    id="danger-info",
                    label=f"⚠️ 该操作具有破坏性：{action_description}",
                ),
                UIComponent(
                    type="confirm_dangerous",
                    id="confirm-action",
                    label="确认执行",
                    options=[
                        UIOption(value="confirmed", display_text="确认执行", highlighted=False),
                        UIOption(value="cancelled", display_text="取消", highlighted=False),
                    ],
                ),
            ],
            allow_free_text=False,
            allow_skip=False,
            timeout_hint="30秒内确认",
        )

    @classmethod
    def create_tutorial_hint(
        cls,
        hint_text: str,
        suggestions: List[str],
    ) -> ClarificationUISchema:
        """创建新手教程提示。"""
        options = [UIOption(value=s, display_text=s) for s in suggestions]
        return ClarificationUISchema(
            message_style="tutorial",
            components=[
                UIComponent(
                    type="show_info",
                    id="tutorial-info",
                    label=hint_text,
                ),
                UIComponent(
                    type="single_select",
                    id="tutorial-options",
                    label="建议操作",
                    options=options,
                ),
            ],
            allow_free_text=True,
            allow_skip=True,
            timeout_hint="不限时",
        )

    @classmethod
    def create_progress_indicator(
        cls,
        message: str,
        progress_pct: float = 0.0,
    ) -> ClarificationUISchema:
        """创建进度指示器。"""
        return ClarificationUISchema(
            message_style="info",
            components=[
                UIComponent(
                    type="progress_indicator",
                    id="progress-1",
                    label=message,
                ),
            ],
            allow_free_text=False,
            allow_skip=True,
            timeout_hint="请稍候...",
        )


# ──────────────────────────────────────────────────────────────────────────────
# 降级：旧前端兼容（未知类型 → 文本）
# ──────────────────────────────────────────────────────────────────────────────

class ClarificationUICompat:
    """旧前端兼容性：将未知 UI 类型降级为文本。"""

    KNOWN_TYPES = {
        "single_select", "multi_select", "text_input", "number_input",
        "address_input", "confirm_dangerous", "show_info", "progress_indicator",
        "taskgraph_preview",
    }

    @classmethod
    def downgrade(cls, schema: ClarificationUISchema) -> ClarificationUISchema:
        """将未知组件降级为 show_info 或 text_input。"""
        components = []
        for comp in schema.components:
            if comp.type in cls.KNOWN_TYPES:
                components.append(comp)
            else:
                # 降级为信息展示
                components.append(UIComponent(
                    type="show_info",
                    id=comp.id,
                    label=f"[不支持的组件类型：{comp.type}] {comp.label or ''}",
                ))
        # 如果没有任何可交互组件，添加一个自由文本输入
        if not any(c.type in ("single_select", "multi_select", "text_input",
                               "number_input", "address_input", "confirm_dangerous")
                   for c in components):
            components.append(UIComponent(
                type="text_input",
                id="fallback-input",
                label="请输入您的回复",
                placeholder="自由文本回复",
            ))
            schema.allow_free_text = True

        schema.components = components
        return schema
