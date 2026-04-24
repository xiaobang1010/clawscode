from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
from urllib.parse import urlparse

from src.hooks.types import HookContext, HookDefinition, HookResult

logger = logging.getLogger(__name__)

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("169.254.0.0/16"),
]

_ssrf_whitelist: list[str] = []


def set_ssrf_whitelist(domains: list[str]) -> None:
    global _ssrf_whitelist
    _ssrf_whitelist = domains


def _is_private_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False

        for allowed in _ssrf_whitelist:
            if hostname == allowed or hostname.endswith(f".{allowed}"):
                return False

        import socket
        resolved = socket.getaddrinfo(hostname, None)
        for family, type_, proto, canonname, sockaddr in resolved:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                for network in _PRIVATE_NETWORKS:
                    if ip in network:
                        return True
            except ValueError:
                continue
    except Exception:
        pass

    return False


class HttpHook:
    @staticmethod
    async def execute(hook: HookDefinition, context: HookContext) -> HookResult:
        if _is_private_url(hook.url):
            return HookResult(
                error=f"SSRF 防护: 目标 URL 解析到内网地址 ({hook.url})",
                should_block=True,
            )

        try:
            import httpx
        except ImportError:
            return HookResult(error="httpx is required for HTTP hooks")

        payload = {
            "event": context.event.value,
            "tool_name": context.tool_name,
            "tool_input": context.tool_input,
            "tool_output": context.tool_output,
            "session_id": context.session_id,
            "metadata": context.metadata,
        }

        try:
            async with httpx.AsyncClient(timeout=hook.timeout) as client:
                response = await client.post(
                    hook.url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                should_block = response.status_code == 403

                return HookResult(
                    output=response.text,
                    error=None if 200 <= response.status_code < 300 else f"HTTP {response.status_code}",
                    should_block=should_block,
                    metadata={"status_code": response.status_code},
                )
        except Exception as e:
            if "timeout" in str(e).lower():
                raise asyncio.TimeoutError()
            return HookResult(error=f"HTTP hook failed: {e}")
