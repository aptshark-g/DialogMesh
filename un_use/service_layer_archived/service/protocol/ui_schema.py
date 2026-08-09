# -*- coding: utf-8 -*-
"""
service/protocol/ui_schema.py
─────────────────────────────
Clarification UI 渲染协议（§13.2）。

定义前端如何渲染多轮澄清交互组件：选择器、输入框、信息展示、进度指示等。
所有模型使用 Pydantic v2 语法，同时提供 `.dict()` 向下兼容。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

# ═══════════════════════════════════════════════════════════════════════════════
# 组件类型常量（字符串，便于前端识别和 JSON 序列化）
# ═══════════════════════════════════════════════════════════════════════════════

SINGLE_SELECT: str = "single_select"
"""单选组件，如按钮组或下拉框"""
MULTI_SELECT: str = "multi_select"
"""多选组件，如复选框组或标签选择器"""
TEXT_INPUT: str = "text_input"
"""自由文本输入框"""
NUMBER_INPUT: str = "number_input"
"""数值输入框（提交值为字符串，服务端再解析）"""
ADDRESS_INPUT: str = "address_input"
"""内存地址输入框（带 0x 前缀校验）"""
CONFIRM_DANGEROUS: str = "confirm_dangerous"
"""危险操作二次确认，如修改内存"""
SHOW_INFO: str = "show_info"
"""只读信息展示卡片"""
PROGRESS_INDICATOR: str = "progress_indicator"
"""进度条或动画指示器（只读）"""
TASKGRAPH_PREVIEW: str = "taskgraph_preview"
"""简化 DAG 图预览（只读，可点击节点）"""


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic BaseModel 兼容层（支持 V1 风格的 .dict() 调用）
# ═══════════════════════════════════════════════════════════════════════════════

class _CompatModel(BaseModel):
    """兼容基类：为 Pydantic v2 模型提供 V1 风格的 `.dict()` 方法。"""

    def dict(self, **kwargs) -> Dict[str, Any]:
        return self.model_dump(**kwargs)

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# UI 组件模型
# ═══════════════════════════════════════════════════════════════════════════════

class UIOption(_CompatModel):
    """单个选项定义，用于选择型组件（单选/多选）。"""

    value: str = Field(..., description="提交给服务端时的值")
    display_text: str = Field(..., description="前端展示文案")
    description: Optional[str] = Field(None, description="悬停提示或副标题")
    icon: Optional[str] = Field(None, description="图标标识（前端映射到具体图标）")
    highlighted: bool = Field(False, description="是否高亮（推荐选项）")


class UIValidation(_CompatModel):
    """输入校验规则，用于文本/数值输入型组件。"""

    type: str = Field(
        ...,
        description="校验类型：regex / range / enum / required",
    )
    pattern: Optional[str] = Field(None, description="regex 模式字符串（type=regex 时必填）")
    min: Optional[float] = Field(None, description="数值最小值（type=range 时可用）")
    max: Optional[float] = Field(None, description="数值最大值（type=range 时可用）")
    error_message: str = Field("输入无效，请重新填写", description="校验失败时展示的错误文案")


class UIComponent(_CompatModel):
    """单个 UI 组件定义，前端按顺序渲染 components 列表。"""

    type: str = Field(
        ...,
        description="组件类型，如 single_select / text_input / show_info 等",
    )
    id: str = Field(..., description="组件唯一标识，用于前端事件回调和数据绑定")
    label: Optional[str] = Field(None, description="组件标签或标题")
    options: Optional[List[UIOption]] = Field(None, description="选择型组件的选项列表")
    placeholder: Optional[str] = Field(None, description="输入型组件的占位提示文案")
    default_value: Optional[str] = Field(None, description="组件默认值")
    validation: Optional[UIValidation] = Field(None, description="输入校验规则（输入型组件适用）")


class ClarificationUISchema(_CompatModel):
    """Clarification 前端渲染协议根对象。

    当解析引擎检测到歧义时，通过此 Schema 指示前端如何渲染交互组件。
    前端只需按顺序渲染 `components` 列表，并遵守全局行为标志。
    """

    version: str = Field("1.0", description="协议版本号，用于向后兼容")
    message_style: str = Field(
        "default",
        description="消息展示风格：default / warning / info / tutorial",
    )
    components: List[UIComponent] = Field(
        default_factory=list,
        description="交互组件列表，前端按顺序渲染",
    )
    allow_free_text: bool = Field(
        True,
        description="是否允许自由文本回复（除选择组件外）",
    )
    allow_skip: bool = Field(
        False,
        description="是否允许用户跳过此澄清（非必填）",
    )
    timeout_hint: str = Field(
        "60秒内回复",
        description="超时提示文案，展示给用户",
    )
