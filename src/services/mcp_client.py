from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


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


@dataclass
class OAuthToken:
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "Bearer"
    expires_at: float = 0.0
    scope: str = ""

    @property
    def is_expired(self) -> bool:
        if not self.access_token:
            return True
        return time.time() >= self.expires_at

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OAuthToken:
        return cls(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            token_type=data.get("token_type", "Bearer"),
            expires_at=data.get("expires_at", 0.0),
            scope=data.get("scope", ""),
        )


@dataclass
class ElicitationRequest:
    message: str
    url: str
    elicitation_id: str = ""
    mode: str = "url"


@dataclass
class MCPServerHealth:
    server_name: str
    is_healthy: bool = False
    last_ping_at: float = 0.0
    last_error: str = ""
    reconnect_count: int = 0


class MCPOAuthProvider:
    def __init__(self, token_storage_path: Path | None = None) -> None:
        self._tokens: dict[str, OAuthToken] = {}
        self._token_storage_path = token_storage_path or Path.home() / ".clawscode" / "mcp_oauth_tokens.json"
        self._pending_requests: dict[str, asyncio.Future[str]] = {}

    def _server_token_key(self, server_name: str) -> str:
        return hashlib.sha256(server_name.encode()).hexdigest()[:16]

    def _load_tokens(self) -> None:
        if self._token_storage_path.exists():
            try:
                data = json.loads(self._token_storage_path.read_text(encoding="utf-8"))
                for key, token_data in data.items():
                    self._tokens[key] = OAuthToken.from_dict(token_data)
            except Exception as e:
                logger.warning(f"[MCP OAuth] 加载令牌失败: {e}")

    def _save_tokens(self) -> None:
        try:
            self._token_storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {key: token.to_dict() for key, token in self._tokens.items()}
            self._token_storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[MCP OAuth] 保存令牌失败: {e}")

    def get_token(self, server_name: str) -> OAuthToken | None:
        key = self._server_token_key(server_name)
        return self._tokens.get(key)

    def store_token(self, server_name: str, token: OAuthToken) -> None:
        key = self._server_token_key(server_name)
        self._tokens[key] = token
        self._save_tokens()

    def clear_token(self, server_name: str) -> None:
        key = self._server_token_key(server_name)
        self._tokens.pop(key, None)
        self._save_tokens()

    async def start_oauth_flow(
        self,
        server_name: str,
        authorize_url: str,
        token_url: str,
        client_id: str,
        client_secret: str = "",
        redirect_uri: str = "http://localhost:9876/callback",
        scope: str = "",
        extra_params: dict | None = None,
    ) -> OAuthToken:
        state = hashlib.sha256(f"{server_name}:{time.time()}".encode()).hexdigest()[:16]

        params: dict[str, str] = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
        }
        if scope:
            params["scope"] = scope
        if extra_params:
            params.update(extra_params)

        parsed = urlparse(authorize_url)
        query = parse_qs(parsed.query)
        query.update({k: [v] for k, v in params.items()})
        new_query = urlencode({k: v[0] for k, v in query.items()})
        full_url = urlunparse(parsed._replace(query=new_query))

        future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self._pending_requests[state] = future

        try:
            webbrowser.open(full_url)
            logger.info(f"[MCP OAuth] 已在浏览器中打开授权页面: {full_url}")

            auth_code = await asyncio.wait_for(future, timeout=300.0)

            async with httpx.AsyncClient() as http_client:
                token_resp = await http_client.post(
                    token_url,
                    data={
                        "grant_type": "authorization_code",
                        "code": auth_code,
                        "redirect_uri": redirect_uri,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )
                token_resp.raise_for_status()
                token_data = token_resp.json()

            expires_in = token_data.get("expires_in", 3600)
            token = OAuthToken(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token", ""),
                token_type=token_data.get("token_type", "Bearer"),
                expires_at=time.time() + expires_in,
                scope=token_data.get("scope", scope),
            )
            self.store_token(server_name, token)
            return token
        except asyncio.TimeoutError:
            raise RuntimeError(f"[MCP OAuth] 授权超时: {server_name}")
        finally:
            self._pending_requests.pop(state, None)

    async def refresh_token(
        self,
        server_name: str,
        token_url: str,
        client_id: str,
        client_secret: str = "",
    ) -> OAuthToken:
        token = self.get_token(server_name)
        if not token or not token.refresh_token:
            raise ValueError(f"[MCP OAuth] 无可刷新的令牌: {server_name}")

        async with httpx.AsyncClient() as http_client:
            resp = await http_client.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token.refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        expires_in = token_data.get("expires_in", 3600)
        new_token = OAuthToken(
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token", token.refresh_token),
            token_type=token_data.get("token_type", "Bearer"),
            expires_at=time.time() + expires_in,
            scope=token_data.get("scope", token.scope),
        )
        self.store_token(server_name, new_token)
        return new_token

    def resolve_callback(self, state: str, code: str) -> None:
        future = self._pending_requests.get(state)
        if future and not future.done():
            future.set_result(code)

    async def ensure_valid_token(
        self,
        server_name: str,
        token_url: str,
        client_id: str,
        client_secret: str = "",
        buffer_seconds: int = 60,
    ) -> OAuthToken | None:
        token = self.get_token(server_name)
        if not token:
            return None
        if token.expires_at - buffer_seconds > time.time():
            return token
        if token.refresh_token:
            try:
                return await self.refresh_token(server_name, token_url, client_id, client_secret)
            except Exception as e:
                logger.warning(f"[MCP OAuth] 刷新令牌失败: {e}")
                return None
        return None


class MCPElicitationHandler:
    def __init__(self) -> None:
        self._pending: dict[str, ElicitationRequest] = {}
        self._results: dict[str, dict] = {}
        self._callback: Any = None

    def set_callback(self, callback: Any) -> None:
        self._callback = callback

    async def handle_elicitation(self, request: ElicitationRequest) -> dict:
        self._pending[request.elicitation_id] = request

        if self._callback:
            result = await self._callback(request)
            self._results[request.elicitation_id] = result
            self._pending.pop(request.elicitation_id, None)
            return result

        self._pending.pop(request.elicitation_id, None)
        return {
            "action": "accept",
            "content": {
                "url": request.url,
                "mode": request.mode,
            },
        }

    def get_pending(self) -> list[ElicitationRequest]:
        return list(self._pending.values())

    def resolve(self, elicitation_id: str, result: dict) -> None:
        self._results[elicitation_id] = result
        self._pending.pop(elicitation_id, None)


class MCPClient:
    MAX_RECONNECT_ATTEMPTS = 3
    RECONNECT_DELAY_SECONDS = 2.0
    HEALTH_CHECK_INTERVAL_SECONDS = 30.0

    def __init__(self, servers: dict[str, dict]) -> None:
        self.servers = servers
        self.sessions: dict[str, ClientSession] = {}
        self._streams: dict[str, tuple] = {}
        self._tool_to_server: dict[str, str] = {}
        self._available_tools: list[dict] = []
        self._allow_rules: list[MCPPermissionRule] = []
        self._deny_rules: list[MCPPermissionRule] = []

        self._oauth_provider = MCPOAuthProvider()
        self._elicitation_handler = MCPElicitationHandler()
        self._health_status: dict[str, MCPServerHealth] = {}
        self._health_task: asyncio.Task | None = None
        self._oauth_configs: dict[str, dict] = {}
        self._shutting_down = False

        for name in servers:
            self._health_status[name] = MCPServerHealth(server_name=name)

        oauth_cfg = servers.get("_oauth", {})
        for server_name, oauth_data in oauth_cfg.items():
            if isinstance(oauth_data, dict) and "client_id" in oauth_data:
                self._oauth_configs[server_name] = oauth_data

        self._oauth_provider._load_tokens()

    @property
    def oauth_provider(self) -> MCPOAuthProvider:
        return self._oauth_provider

    @property
    def elicitation_handler(self) -> MCPElicitationHandler:
        return self._elicitation_handler

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

    def _get_server_config(self, name: str) -> dict:
        config = self.servers.get(name, {})
        if not isinstance(config, dict):
            return {}
        return config

    async def _connect_server(self, name: str) -> bool:
        config = self._get_server_config(name)
        if not config or "command" not in config:
            return False

        try:
            env = dict(config.get("env") or {})

            oauth_cfg = self._oauth_configs.get(name)
            if oauth_cfg:
                token = await self._oauth_provider.ensure_valid_token(
                    server_name=name,
                    token_url=oauth_cfg.get("token_url", ""),
                    client_id=oauth_cfg.get("client_id", ""),
                    client_secret=oauth_cfg.get("client_secret", ""),
                )
                if token:
                    env["MCP_OAUTH_TOKEN"] = token.access_token

            params = StdioServerParameters(
                command=config["command"],
                args=config.get("args", []),
                env=env if env else None,
            )
            read_stream, write_stream = await stdio_client(params).__aenter__()
            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            await session.initialize()
            self.sessions[name] = session
            self._streams[name] = (read_stream, write_stream)

            health = self._health_status.get(name)
            if health:
                health.is_healthy = True
                health.last_ping_at = time.time()
                health.last_error = ""

            return True
        except Exception as e:
            logger.warning(f"[MCP] 连接 {name} 失败: {e}")
            health = self._health_status.get(name)
            if health:
                health.is_healthy = False
                health.last_error = str(e)
            return False

    async def connect_all(self) -> None:
        for name in self.servers:
            if name.startswith("_"):
                continue
            await self._connect_server(name)

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
                logger.warning(f"[MCP] 获取 {name} 工具列表失败: {e}")
        return tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        if not self.is_tool_allowed(tool_name):
            raise PermissionError(f"MCP 工具 {tool_name} 被权限规则拒绝")

        server_name = self._tool_to_server.get(tool_name)
        if server_name is None:
            raise ValueError(f"未知工具: {tool_name}")

        session = self._get_session_or_reconnect(server_name)
        if session is None:
            raise RuntimeError(f"服务器 {server_name} 未连接")

        try:
            result = await session.call_tool(tool_name, arguments)
        except Exception as e:
            error_str = str(e)
            if self._should_reconnect(error_str):
                session = await self._try_reconnect(server_name)
                if session is None:
                    raise RuntimeError(f"服务器 {server_name} 重连失败") from e
                result = await session.call_tool(tool_name, arguments)
            else:
                raise

        texts: list[str] = []
        for item in result.content:
            if hasattr(item, "text"):
                texts.append(item.text)
        return "\n".join(texts)

    def _should_reconnect(self, error_message: str) -> bool:
        reconnect_hints = [
            "connection closed",
            "connection reset",
            "broken pipe",
            "session closed",
            "not connected",
            "transport error",
        ]
        lower = error_message.lower()
        return any(hint in lower for hint in reconnect_hints)

    def _get_session_or_reconnect(self, server_name: str) -> ClientSession | None:
        return self.sessions.get(server_name)

    async def _try_reconnect(self, server_name: str) -> ClientSession | None:
        health = self._health_status.get(server_name)
        if health:
            health.reconnect_count += 1

        for attempt in range(self.MAX_RECONNECT_ATTEMPTS):
            try:
                old_session = self.sessions.pop(server_name, None)
                if old_session:
                    try:
                        await old_session.__aexit__(None, None, None)
                    except Exception:
                        pass
                self._streams.pop(server_name, None)

                success = await self._connect_server(server_name)
                if success:
                    logger.info(f"[MCP] 重连 {server_name} 成功 (尝试 {attempt + 1})")
                    return self.sessions.get(server_name)
            except Exception as e:
                logger.warning(f"[MCP] 重连 {server_name} 尝试 {attempt + 1} 失败: {e}")

            if attempt < self.MAX_RECONNECT_ATTEMPTS - 1:
                await asyncio.sleep(self.RECONNECT_DELAY_SECONDS * (attempt + 1))

        logger.error(f"[MCP] 重连 {server_name} 失败，已达最大重试次数")
        return None

    async def list_resources(self, server_name: str | None = None) -> list[dict]:
        results: list[dict] = []
        targets = {server_name: self.sessions[server_name]} if server_name and server_name in self.sessions else dict(self.sessions)

        for name, session in targets.items():
            try:
                result = await session.list_resources()
                for resource in result.resources:
                    entry = {
                        "server": name,
                        "name": resource.name,
                        "uri": str(resource.uri),
                        "description": resource.description or "",
                        "mime_type": resource.mimeType or "",
                    }
                    results.append(entry)
            except Exception as e:
                logger.warning(f"[MCP] 获取 {name} 资源列表失败: {e}")

        return results

    async def read_resource(self, server_name: str, uri: str) -> str:
        session = self._get_session_or_reconnect(server_name)
        if session is None:
            raise RuntimeError(f"服务器 {server_name} 未连接")

        from pydantic import AnyUrl

        result = await session.read_resource(AnyUrl(uri))
        contents: list[str] = []
        for item in result.contents:
            if hasattr(item, "text"):
                contents.append(item.text)
            elif hasattr(item, "blob"):
                import base64
                contents.append(base64.b64decode(item.blob).decode("utf-8", errors="replace"))
        return "\n".join(contents)

    async def health_check(self) -> dict[str, MCPServerHealth]:
        for name in list(self.sessions.keys()):
            session = self.sessions.get(name)
            if session is None:
                continue
            try:
                await session.send_ping()
                health = self._health_status.get(name)
                if health:
                    health.is_healthy = True
                    health.last_ping_at = time.time()
                    health.last_error = ""
            except Exception as e:
                health = self._health_status.get(name)
                if health:
                    health.is_healthy = False
                    health.last_error = str(e)
        return dict(self._health_status)

    def start_health_monitor(self) -> None:
        if self._health_task and not self._health_task.done():
            return
        self._shutting_down = False
        self._health_task = asyncio.create_task(self._health_monitor_loop())

    async def _health_monitor_loop(self) -> None:
        while not self._shutting_down:
            try:
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL_SECONDS)
                if self._shutting_down:
                    break

                health_status = await self.health_check()
                for name, health in health_status.items():
                    if not health.is_healthy and name in self.servers:
                        logger.info(f"[MCP] 检测到 {name} 不健康，尝试自动重连...")
                        await self._try_reconnect(name)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[MCP] 健康监控异常: {e}")

    def stop_health_monitor(self) -> None:
        self._shutting_down = True
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()

    async def disconnect_all(self) -> None:
        self.stop_health_monitor()
        for name, session in self.sessions.items():
            try:
                await session.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"[MCP] 断开 {name} 失败: {e}")
        self.sessions.clear()
        self._streams.clear()
        self._tool_to_server.clear()
        self._available_tools.clear()

    def get_status(self) -> dict[str, str]:
        status: dict[str, str] = {}
        for name in self.servers:
            if name.startswith("_"):
                continue
            health = self._health_status.get(name)
            if name in self.sessions:
                if health and health.is_healthy:
                    status[name] = "connected"
                else:
                    status[name] = "degraded"
            else:
                status[name] = "disconnected"
        return status

    def get_permission_rules(self) -> dict[str, list[str]]:
        return {
            "allow": [r.to_string() for r in self._allow_rules],
            "deny": [r.to_string() for r in self._deny_rules],
        }

    def get_health_status(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for name, health in self._health_status.items():
            result[name] = {
                "is_healthy": health.is_healthy,
                "last_ping_at": health.last_ping_at,
                "last_error": health.last_error,
                "reconnect_count": health.reconnect_count,
            }
        return result
