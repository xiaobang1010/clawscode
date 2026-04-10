from __future__ import annotations

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    def __init__(self, servers: dict[str, dict]) -> None:
        self.servers = servers
        self.sessions: dict[str, ClientSession] = {}
        self._streams: dict[str, tuple] = {}
        self._tool_to_server: dict[str, str] = {}
        self._available_tools: list[dict] = []

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
                    tools.append(entry)
                    self._tool_to_server[tool.name] = name
                    self._available_tools.append(entry)
            except Exception as e:
                print(f"[MCP] 获取 {name} 工具列表失败: {e}")
        return tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
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
