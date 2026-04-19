from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class McpAuthInput(BaseModel):
    action: str = Field(description="操作类型: login/logout/status")
    server_name: str = Field(description="MCP 服务器名称")
    authorize_url: str = Field(default="", description="OAuth 授权端点 URL（login 时必填）")
    token_url: str = Field(default="", description="OAuth 令牌端点 URL（login 时必填）")
    client_id: str = Field(default="", description="OAuth 客户端 ID（login 时必填）")
    client_secret: str = Field(default="", description="OAuth 客户端密钥")
    redirect_uri: str = Field(default="http://localhost:9876/callback", description="OAuth 重定向 URI")
    scope: str = Field(default="", description="OAuth 权限范围")


class McpAuthTool(Tool):
    name = "McpAuthTool"
    description = "管理 MCP 服务器的 OAuth 认证。支持 login（发起 OAuth 授权流程）、logout（清除令牌）、status（查看认证状态）操作。"
    input_schema = McpAuthInput
    is_readonly = False

    async def call(self, input: McpAuthInput, context: Any) -> ToolResult:
        mcp_client = getattr(context, "mcp_client", None)
        if mcp_client is None:
            return ToolResult(output="MCP 客户端未初始化", is_error=True)

        if input.action == "login":
            return await self._login(mcp_client, input)
        elif input.action == "logout":
            return self._logout(mcp_client, input.server_name)
        elif input.action == "status":
            return self._status(mcp_client, input.server_name)
        else:
            return ToolResult(output=f"未知操作: {input.action}，支持: login/logout/status", is_error=True)

    async def _login(self, mcp_client: Any, input: McpAuthInput) -> ToolResult:
        if not input.authorize_url or not input.token_url or not input.client_id:
            return ToolResult(output="login 操作需要提供 authorize_url、token_url 和 client_id", is_error=True)

        try:
            token = await mcp_client.oauth_provider.start_oauth_flow(
                server_name=input.server_name,
                authorize_url=input.authorize_url,
                token_url=input.token_url,
                client_id=input.client_id,
                client_secret=input.client_secret,
                redirect_uri=input.redirect_uri,
                scope=input.scope,
            )
            return ToolResult(
                output=f"OAuth 认证成功\n服务器: {input.server_name}\n令牌类型: {token.token_type}\n过期时间: {'%.0f' % token.expires_at}\n权限范围: {token.scope or '(默认)'}"
            )
        except Exception as e:
            return ToolResult(output=f"OAuth 认证失败: {e}", is_error=True)

    def _logout(self, mcp_client: Any, server_name: str) -> ToolResult:
        token = mcp_client.oauth_provider.get_token(server_name)
        if token is None:
            return ToolResult(output=f"服务器 {server_name} 无已存储的认证令牌")
        mcp_client.oauth_provider.clear_token(server_name)
        return ToolResult(output=f"已清除服务器 {server_name} 的认证令牌")

    def _status(self, mcp_client: Any, server_name: str) -> ToolResult:
        token = mcp_client.oauth_provider.get_token(server_name)
        if token is None:
            return ToolResult(output=f"服务器 {server_name}: 未认证")

        import time

        remaining = token.expires_at - time.time()
        status = "已过期" if token.is_expired else f"剩余 {'%.0f' % remaining} 秒"

        lines = [
            f"服务器: {server_name}",
            f"状态: {'已认证' if not token.is_expired else '令牌已过期'}",
            f"令牌类型: {token.token_type}",
            f"过期: {status}",
            f"权限范围: {token.scope or '(默认)'}",
            f"支持刷新: {'是' if token.refresh_token else '否'}",
        ]
        return ToolResult(output="\n".join(lines))
