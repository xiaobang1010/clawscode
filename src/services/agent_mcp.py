from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class AgentMcpServerSpec:
    name: str
    transport: Literal["stdio", "sse", "websocket"] = "stdio"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    disabled: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentMcpServerSpec:
        return cls(
            name=data.get("name", ""),
            transport=data.get("transport", "stdio"),
            command=data.get("command"),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=data.get("url"),
            headers=data.get("headers", {}),
            disabled=data.get("disabled", False),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name, "transport": self.transport}
        if self.command:
            result["command"] = self.command
        if self.args:
            result["args"] = self.args
        if self.env:
            result["env"] = self.env
        if self.url:
            result["url"] = self.url
        if self.headers:
            result["headers"] = self.headers
        if self.disabled:
            result["disabled"] = self.disabled
        return result

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name:
            errors.append("MCP server name is required")
        if self.transport == "stdio":
            if not self.command:
                errors.append(f"stdio transport requires 'command' for server '{self.name}'")
        elif self.transport in ("sse", "websocket"):
            if not self.url:
                errors.append(f"{self.transport} transport requires 'url' for server '{self.name}'")
        return errors


@dataclass
class AgentMcpConfig:
    servers: list[AgentMcpServerSpec] = field(default_factory=list)
    references: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AgentMcpConfig | None:
        if data is None:
            return None
        servers = []
        references = []
        if "servers" in data:
            for s in data["servers"]:
                if isinstance(s, str):
                    references.append(s)
                elif isinstance(s, dict):
                    servers.append(AgentMcpServerSpec.from_dict(s))
        if "references" in data:
            references.extend(data["references"])
        return cls(servers=servers, references=list(set(references)))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.servers:
            result["servers"] = [s.to_dict() for s in self.servers]
        if self.references:
            result["references"] = self.references
        return result

    def validate(self) -> list[str]:
        errors: list[str] = []
        for server in self.servers:
            errors.extend(server.validate())
        return errors

    def get_all_server_names(self) -> list[str]:
        names = [s.name for s in self.servers if not s.disabled]
        names.extend(self.references)
        return list(set(names))


class AgentMcpConnectionManager:
    def __init__(self):
        self._connections: dict[str, Any] = {}

    async def connect(self, spec: AgentMcpServerSpec) -> Any:
        if spec.name in self._connections:
            return self._connections[spec.name]
        return None

    async def disconnect(self, name: str) -> None:
        if name in self._connections:
            del self._connections[name]

    async def disconnect_all(self) -> None:
        self._connections.clear()

    def get_connection(self, name: str) -> Any | None:
        return self._connections.get(name)


def resolve_agent_mcp_config(
    agent_config: AgentMcpConfig | None,
    global_mcp_servers: dict[str, Any] | None,
) -> list[AgentMcpServerSpec]:
    if agent_config is None:
        return []
    result: list[AgentMcpServerSpec] = []
    result.extend(agent_config.servers)
    if global_mcp_servers and agent_config.references:
        for ref in agent_config.references:
            if ref in global_mcp_servers:
                server_data = global_mcp_servers[ref]
                if isinstance(server_data, dict):
                    server_data = dict(server_data)
                    server_data["name"] = ref
                    result.append(AgentMcpServerSpec.from_dict(server_data))
    return [s for s in result if not s.disabled]
