from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class ListMcpResourcesInput(BaseModel):
    server_name: str = Field(default="", description="MCP 服务器名称（为空则列出所有服务器的资源）")


class ListMcpResourcesTool(Tool):
    name = "ListMcpResourcesTool"
    description = "列出 MCP 服务器提供的资源。可指定服务器名称，或留空列出所有已连接服务器的资源。"
    input_schema = ListMcpResourcesInput
    is_readonly = True

    async def call(self, input: ListMcpResourcesInput, context: Any) -> ToolResult:
        mcp_client = getattr(context, "mcp_client", None)
        if mcp_client is None:
            return ToolResult(output="MCP 客户端未初始化", is_error=True)

        server_name = input.server_name or None
        if server_name and server_name not in mcp_client.sessions:
            available = ", ".join(mcp_client.sessions.keys()) if mcp_client.sessions else "(无)"
            return ToolResult(output=f"服务器 {server_name} 未连接。可用服务器: {available}", is_error=True)

        try:
            resources = await mcp_client.list_resources(server_name)
        except Exception as e:
            return ToolResult(output=f"获取资源列表失败: {e}", is_error=True)

        if not resources:
            scope = f"服务器 {server_name}" if server_name else "所有服务器"
            return ToolResult(output=f"{scope} 暂无可用资源")

        lines: list[str] = []
        current_server: str | None = None
        for res in sorted(resources, key=lambda r: (r["server"], r["name"])):
            if res["server"] != current_server:
                current_server = res["server"]
                lines.append(f"\n== 服务器: {current_server} ==")
            desc = f" - {res['description']}" if res.get("description") else ""
            mime = f" [{res['mime_type']}]" if res.get("mime_type") else ""
            lines.append(f"  {res['name']}: {res['uri']}{mime}{desc}")

        return ToolResult(output="\n".join(lines))
