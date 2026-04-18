from __future__ import annotations

import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult

_preapproved_domains: list[str] = []


def load_preapproved_urls(settings: Any) -> None:
    global _preapproved_domains
    urls = getattr(settings, 'preapproved_urls', None) or getattr(settings, 'web_fetch_preapproved', None) or []
    _preapproved_domains = urls


def _is_preapproved(url: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""
    for pattern in _preapproved_domains:
        if pattern.startswith("*."):
            if host.endswith(pattern[2:]) or host == pattern[2:]:
                return True
        elif host == pattern:
            return True
    return False


def _html_to_markdown(html: str) -> str:
    text = html
    text = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", lambda m: "#" * int(m.group(1)) + " " + m.group(2).strip(), text, flags=re.DOTALL)
    text = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", text, flags=re.DOTALL)
    text = re.sub(r"<a[^>]*href=[\"']([^\"']*)[\"'][^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.DOTALL)
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.DOTALL)
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)
    text = re.sub(r"<pre[^>]*>(.*?)</pre>", r"```\n\1\n```", text, flags=re.DOTALL)
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1", text, flags=re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class WebFetchInput(BaseModel):
    url: str = Field(description="要抓取的 URL")
    max_length: int = Field(default=50000, description="返回内容的最大字符数")


class WebFetchTool(Tool):
    name = "WebFetch"
    description = "抓取 URL 内容并转换为 Markdown 格式返回"
    input_schema = WebFetchInput
    is_readonly = True
    max_result_size_chars = 50000

    async def call(self, input: WebFetchInput, context: Any) -> ToolResult:
        url = input.url.strip()
        if url.startswith("http://"):
            url = "https://" + url[7:]

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": "ClawsCode/0.1.0"})
                response.raise_for_status()
        except httpx.TimeoutException:
            return ToolResult(output="请求超时", is_error=True)
        except httpx.HTTPStatusError as e:
            return ToolResult(output=f"HTTP 错误: {e.response.status_code}", is_error=True)
        except Exception as e:
            return ToolResult(output=f"请求失败: {e}", is_error=True)

        content_type = response.headers.get("content-type", "")
        body = response.text

        if "text/html" in content_type:
            body = _html_to_markdown(body)
        elif "application/json" in content_type:
            pass
        elif "text/" not in content_type:
            return ToolResult(output=f"不支持的内容类型: {content_type}", is_error=True)

        max_len = input.max_length
        if len(body) > max_len:
            body = body[:max_len] + f"\n\n...[截断，已显示 {max_len} / {len(body)} 字符]"

        if _preapproved_domains:
            preapproved = _is_preapproved(url)
            if preapproved:
                body += "\n\n[预批准 URL]"

        return ToolResult(output=body)
