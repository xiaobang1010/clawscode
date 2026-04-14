from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class ToolSearchInput(BaseModel):
    query: str = Field(description="搜索关键词")


class ToolSearchTool(Tool):
    name = "ToolSearch"
    description = "搜索可用工具。返回匹配工具的名称、描述和参数信息。"
    input_schema = ToolSearchInput
    is_readonly = True
    is_lazy = True

    async def call(self, input: ToolSearchInput, context: Any) -> ToolResult:
        from src.tools import get_tools

        tools = get_tools()
        extra_tools = getattr(context, "_extra_tools", [])
        all_tools = tools + extra_tools

        query_lower = input.query.lower()
        matches = []
        for tool in all_tools:
            t_name = getattr(tool, "name", "")
            t_desc = getattr(tool, "description", "")
            if query_lower in t_name.lower() or query_lower in t_desc.lower():
                schema = tool.get_json_schema() if hasattr(tool, "get_json_schema") else {}
                matches.append(f"- **{t_name}**: {t_desc}\n  参数: {schema}")

        if not matches:
            return ToolResult(output=f"未找到与 '{input.query}' 匹配的工具")

        return ToolResult(output=f"找到 {len(matches)} 个匹配工具:\n\n" + "\n\n".join(matches))
