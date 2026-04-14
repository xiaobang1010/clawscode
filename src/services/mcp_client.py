from __future__ import annotations

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPPermissionRule:
    def __init__(self, server_name: str, tool_name: str = "*", pattern: str = "*"):
        self.server_name = server_name
        self.tool_name = tool_name
        self.pattern = pattern

    def matches(self, server_name: str, tool_name: str) -> bool:
        if self.server_name != "*" and self.server_name != server_name:
            return False
        if self.tool_name != "*" and self.tool_name != tool_name:
            return False
        return True

    def to_string(self) -> str:
        parts = ["MCP", self.server_name]
        if self.tool_name != "*":
            parts.append(self.tool_name)
        if self.pattern != "*":
            parts.append(self.pattern)
        return ":".join(parts)


class MCPClient:
    def __init__(self, servers: dict[str, dict]) -> None:
        self.servers = servers
        self.sessions: dict[str, ClientSession] = {}
        self._streams: dict[str, tuple] = {}
        self._tool_to_server: dict[str, str] = {}
        self._available_tools: list[dict] = []
        self._allow_rules: list[MCPPermissionRule] = []
        self._deny_rules: list[MCPPermissionRule] = []

    def add_allow_rule(self, server_name: str, tool_name: str = "*") -> None:
        rule = MCPPermissionRule(server_name, tool_name)
        if rule not in self._allow_rules:
            self._allow_rules.append(rule)

    def add_deny_rule(self, server_name: str, tool_name: str = "*") -> None:
        rule = MCPPermissionRule(server_name, tool_name)
        if rule not in self._deny_rules:
            self._deny_rules.append(rule)

    def is_tool_allowed(self, tool_name: str) -> bool:
        server_name = self._tool_to_server.get(tool_name, "")
        for rule in self._deny_rules:
            if rule.matches(server_name, tool_name):
                return False
        for rule in self._allow_rules:
            if rule.matches(server_name, tool_name):
                return True
        return True

    async def connect_all(self) -> None:
        for name, config in self.servers.items():
            try:
                params = StdioServerParameters(
                    command=config["command"],
                    args=config.get("args", []),
                    env=config.get("env"),
                )
                read_stream, write_stream = await stdio_client(params).__aenter__()
                session = ClientSession(read_stream, write_stream)
                await session.__aenter__()
                await session.initialize()
                self.sessions[name] = session
                self._streams[name] = (read_stream, write_stream)
            except Exception as e:
                print(f"[MCP] 连接 {name} 失败: {e}")

    async def list_tools(self) -> list[dict]:
        self._tool_to_server.clear()
        self._available_tools.clear()
        tools: list[dict] = []
        for name, session in self.sessions.items():
            try:
                result = await session.list_tools()
                for tool in result.tools:
                    entry = {
                        "server": name,
                        "name": tool.name,
                        "description": tool.description,
                        "schema": tool.inputSchema,
                    }
                    self._tool_to_server[tool.name] = name
                    self._available_tools.append(entry)
                    if self.is_tool_allowed(tool.name):
                        tools.append(entry)
            except Exception as e:
                print(f"[MCP] 获取 {name} 工具列表失败: {e}")
        return tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        if not self.is_tool_allowed(tool_name):
            raise PermissionError(f"MCP 工具 {tool_name} 被权限规则拒绝")

        server_name = self._tool_to_server.get(tool_name)
        if server_name is None:
            raise ValueError(f"未知工具: {tool_name}")
        session = self.sessions.get(server_name)
        if session is None:
            raise RuntimeError(f"服务器 {server_name} 未连接")
        result = await session.call_tool(tool_name, arguments)
        texts: list[str] = []
        for item in result.content:
            if hasattr(item, "text"):
                texts.append(item.text)
        return "\n".join(texts)

    async def disconnect_all(self) -> None:
        for name, session in self.sessions.items():
            try:
                await session.__aexit__(None, None, None)
            except Exception as e:
                print(f"[MCP] 断开 {name} 失败: {e}")
        self.sessions.clear()
        self._streams.clear()
        self._tool_to_server.clear()
        self._available_tools.clear()

    def get_status(self) -> dict[str, str]:
        status: dict[str, str] = {}
        for name in self.servers:
            status[name] = "connected" if name in self.sessions else "disconnected"
        return status

    def get_permission_rules(self) -> dict[str, list[str]]:
        return {
            "allow": [r.to_string() for r in self._allow_rules],
            "deny": [r.to_string() for r in self._deny_rules],
        }
