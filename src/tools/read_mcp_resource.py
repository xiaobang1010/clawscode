from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class ReadMcpResourceInput(BaseModel):
    server_name: str = Field(description="MCP 服务器名称")
    uri: str = Field(description="资源 URI")


class ReadMcpResourceTool(Tool):
    name = "ReadMcpResourceTool"
    description = "读取 MCP 服务器上的指定资源内容。需要提供服务名称和资源 URI。"
    input_schema = ReadMcpResourceInput
    is_readonly = True
    max_result_size_chars = 50000

    async def call(self, input: ReadMcpResourceInput, context: Any) -> ToolResult:
        mcp_client = getattr(context, "mcp_client", None)
        if mcp_client is None:
            return ToolResult(output="MCP 客户端未初始化", is_error=True)

        if input.server_name not in mcp_client.sessions:
            available = ", ".join(mcp_client.sessions.keys()) if mcp_client.sessions else "(无)"
            return ToolResult(output=f"服务器 {input.server_name} 未连接。可用服务器: {available}", is_error=True)

        try:
            content = await mcp_client.read_resource(input.server_name, input.uri)
        except Exception as e:
            return ToolResult(output=f"读取资源失败: {e}", is_error=True)

        header = f"== 资源: {input.uri} (来自 {input.server_name}) ==\n\n"
        return ToolResult.from_output(header + content, max_chars=self.max_result_size_chars)
