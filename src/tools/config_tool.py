from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class ConfigToolInput(BaseModel):
    action: str = Field(description="操作类型: get/set/list")
    key: str = Field(default="", description="配置项名称")
    value: str = Field(default="", description="配置项值（set 操作时使用）")


SUPPORTED_SETTINGS = {
    "model": str,
    "permission_mode": str,
    "max_tokens": int,
}


class ConfigTool(Tool):
    name = "ConfigTool"
    description = "查看或修改运行时配置项。支持 get/set/list 操作。可配置项: model, permission_mode, max_tokens。"
    input_schema = ConfigToolInput

    async def call(self, input: ConfigToolInput, context: Any) -> ToolResult:
        if input.action == "list":
            return self._list_settings(context)
        elif input.action == "get":
            return self._get_setting(input.key, context)
        elif input.action == "set":
            return self._set_setting(input.key, input.value, context)
        else:
            return ToolResult(output=f"未知操作: {input.action}，支持: get/set/list", is_error=True)

    def _list_settings(self, context: Any) -> ToolResult:
        lines = ["当前配置:"]
        settings = context.settings
        for key in SUPPORTED_SETTINGS:
            val = getattr(settings, key, "<未设置>")
            lines.append(f"  {key} = {val}")
        return ToolResult(output="\n".join(lines))

    def _get_setting(self, key: str, context: Any) -> ToolResult:
        if key not in SUPPORTED_SETTINGS:
            return ToolResult(output=f"未知配置项: {key}，支持: {', '.join(SUPPORTED_SETTINGS)}", is_error=True)
        val = getattr(context.settings, key, "<未设置>")
        return ToolResult(output=f"{key} = {val}")

    def _set_setting(self, key: str, value: str, context: Any) -> ToolResult:
        if key not in SUPPORTED_SETTINGS:
            return ToolResult(output=f"未知配置项: {key}，支持: {', '.join(SUPPORTED_SETTINGS)}", is_error=True)

        expected_type = SUPPORTED_SETTINGS[key]
        try:
            if expected_type == int:
                converted = int(value)
            else:
                converted = str(value)
        except ValueError:
            return ToolResult(output=f"无效值: {value}，期望类型: {expected_type.__name__}", is_error=True)

        old_value = getattr(context.settings, key, None)
        setattr(context.settings, key, converted)
        return ToolResult(output=f"已更新 {key}: {old_value} -> {converted}")
