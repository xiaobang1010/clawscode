from __future__ import annotations

import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class WebSearchInput(BaseModel):
    query: str = Field(description="搜索查询关键词")
    num_results: int = Field(default=5, description="返回结果数量，最多10条")


class WebSearchTool(Tool):
    name = "WebSearch"
    description = "在网络上搜索信息，返回搜索结果列表"
    input_schema = WebSearchInput
    is_readonly = True

    async def call(self, input: WebSearchInput, context: Any) -> ToolResult:
        num = min(input.num_results, 10)
        api_key = getattr(context.settings, "web_search_api_key", "") or ""
        engine_id = getattr(context.settings, "web_search_engine_id", "") or ""

        if api_key and engine_id:
            return await self._google_search(input.query, num, api_key, engine_id)

        return await self._duckduckgo_search(input.query, num)

    async def _google_search(self, query: str, num: int, api_key: str, engine_id: str) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={"key": api_key, "cx": engine_id, "q": query, "num": num},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return ToolResult(output=f"搜索失败: {e}", is_error=True)

        items = data.get("items", [])
        if not items:
            return ToolResult(output="未找到搜索结果")

        results = []
        for i, item in enumerate(items, 1):
            results.append(f"{i}. [{item.get('title', '')}]({item.get('link', '')})\n   {item.get('snippet', '')}")

        return ToolResult(output="\n\n".join(results))

    async def _duckduckgo_search(self, query: str, num: int) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (compatible; ClawsCode/0.1.0)"},
                )
                resp.raise_for_status()
        except Exception as e:
            return ToolResult(output=f"搜索失败: {e}", is_error=True)

        results = []
        pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>.*?<a class="result__snippet"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, resp.text, re.DOTALL)[:num]

        for i, (url, title, snippet) in enumerate(matches, 1):
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            clean_snippet = re.sub(r"<[^>]+>", "", snippet).strip()
            results.append(f"{i}. [{clean_title}]({url})\n   {clean_snippet}")

        if not results:
            return ToolResult(output="未找到搜索结果")

        return ToolResult(output="\n\n".join(results))
