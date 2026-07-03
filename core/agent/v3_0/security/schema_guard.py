# -*- coding: utf-8 -*-

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SchemaGuard:
    """
    SchemaGuard v3.0 -- LLM 输出实时校验器（幻觉防御 Layer 1）。

    职责：
      - JSON 格式合规校验
      - 参数类型与范围约束检查
      - 字段完整性验证
      - 敏感内容过滤
    """

    def __init__(self):
        self._field_schemas: Dict[str, Dict[str, Any]] = {}
        self._blocked_patterns: List[str] = [
            r"(?i)(rm\s+-rf|format\s+[a-z]:|shutdown\s+-s)",
            r"(?i)(DROP|DELETE|TRUNCATE)\s+(TABLE|DATABASE)",
        ]

    def register_schema(self, name: str, schema: Dict[str, Any]) -> None:
        """注册一个字段的校验 Schema。"""
        self._field_schemas[name] = schema

    def validate_json(self, output_text: str) -> Tuple[bool, Optional[Dict[str, Any]], List[str]]:
        """
        校验 JSON 输出格式并返回 (is_valid, parsed, errors)。
        """
        errors: List[str] = []
        text = output_text.strip()
        if not text:
            return (False, None, ["空输出"])

        # 尝试解析 JSON
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # 尝试从 markdown 代码块中提取
            m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(1))
                except json.JSONDecodeError:
                    return (False, None, ["JSON 解析失败: 非法的 JSON 格式"])
            else:
                return (False, None, ["JSON 解析失败: 不是有效的 JSON 格式"])

        return (True, parsed, [])

    def validate_field(self, field_name: str, value: Any) -> Optional[str]:
        """
        校验单个字段的值是否符合注册的 Schema。
        返回错误描述，None 表示通过。
        """
        schema = self._field_schemas.get(field_name)
        if not schema:
            return None

        vtype = schema.get("type", "any")
        vmin = schema.get("min")
        vmax = schema.get("max")
        allowed = schema.get("allowed")

        if vtype == "float" and not isinstance(value, (int, float)):
            return f"字段 {field_name}: 期望 float，得到 {type(value).__name__}"
        if vtype == "int" and not isinstance(value, int):
            return f"字段 {field_name}: 期望 int，得到 {type(value).__name__}"
        if vtype == "str" and not isinstance(value, str):
            return f"字段 {field_name}: 期望 str，得到 {type(value).__name__}"

        if isinstance(value, (int, float)) and vmin is not None and value < vmin:
            return f"字段 {field_name}: 值 {value} 低于最小值 {vmin}"
        if isinstance(value, (int, float)) and vmax is not None and value > vmax:
            return f"字段 {field_name}: 值 {value} 超过最大值 {vmax}"

        if allowed is not None and isinstance(value, str) and value not in allowed:
            return f"字段 {field_name}: 值 {value} 不在允许集合中"

        return None

    def sanitize_output(self, output_text: str) -> Tuple[str, List[str]]:
        """
        过滤输出中的敏感内容（危险命令、注入等）。
        返回 (cleaned_text, warnings)。
        """
        warnings: List[str] = []
        cleaned = output_text
        for pattern in self._blocked_patterns:
            matches = re.findall(pattern, output_text)
            for m in matches:
                warnings.append(f"检测到敏感内容: {m}")
                cleaned = cleaned.replace(m, "[FILTERED]")
        return (cleaned, warnings)

    def validate_structured_output(self, output: Dict[str, Any],
                                      required_fields: List[str],
                                      field_schemas: Optional[Dict[str, Dict[str, Any]]] = None) -> Tuple[bool, List[str]]:
        """
        完整校验结构化输出。
        检查必需字段是否存在，并按 Schema 校验每个字段。
        """
        errors: List[str] = []
        for field in required_fields:
            if field not in output:
                errors.append(f"缺少必需字段: {field}")
        if field_schemas:
            for field_name, value in output.items():
                err = self.validate_field(field_name, value)
                if err:
                    errors.append(err)
        return (len(errors) == 0, errors)


__all__ = ["SchemaGuard"]
