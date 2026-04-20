from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult

logger = logging.getLogger(__name__)

_lsp_clients: dict[str, LSPClient] = {}


class LSPInput(BaseModel):
    operation: str = Field(
        description="操作类型: definition, references, diagnostics, symbol, hover"
    )
    file_path: str = Field(default="", description="文件路径")
    line: int | None = Field(default=None, description="行号（从 1 开始）")
    character: int | None = Field(default=None, description="列号（从 1 开始）")
    query: str | None = Field(default=None, description="符号搜索查询")
    language: str | None = Field(default=None, description="编程语言（用于自动选择 LSP 服务器）")


class LSPClient:
    def __init__(self, command: list[str], cwd: str):
        self._command = command
        self._cwd = cwd
        self._proc: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._initialized = False

    async def start(self) -> bool:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self._command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
            )
            return await self._initialize()
        except (OSError, FileNotFoundError) as e:
            logger.warning("Failed to start LSP server: %s", e)
            return False

    async def _initialize(self) -> bool:
        init_params = {
            "processId": os.getpid(),
            "rootUri": Path(self._cwd).as_uri(),
            "capabilities": {
                "textDocument": {
                    "definition": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                    "hover": {"dynamicRegistration": False, "contentFormat": ["plaintext", "markdown"]},
                    "publishDiagnostics": {"dynamicRegistration": False},
                },
                "workspace": {
                    "symbol": {"dynamicRegistration": False},
                },
            },
        }
        response = await self._send_request("initialize", init_params)
        if response is None:
            return False

        await self._send_notification("initialized", {})
        self._initialized = True
        return True

    async def _send_request(self, method: str, params: dict) -> dict | None:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            return None

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        body = json.dumps(request)
        message = f"Content-Length: {len(body)}\r\n\r\n{body}"

        try:
            self._proc.stdin.write(message.encode("utf-8"))
            await self._proc.stdin.drain()

            return await self._read_response()
        except (ConnectionError, OSError) as e:
            logger.warning("LSP request failed: %s", e)
            return None

    async def _send_notification(self, method: str, params: dict) -> None:
        if self._proc is None or self._proc.stdin is None:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        body = json.dumps(notification)
        message = f"Content-Length: {len(body)}\r\n\r\n{body}"

        try:
            self._proc.stdin.write(message.encode("utf-8"))
            await self._proc.stdin.drain()
        except (ConnectionError, OSError):
            pass

    async def _read_response(self) -> dict | None:
        if self._proc is None or self._proc.stdout is None:
            return None

        try:
            header = await asyncio.wait_for(self._proc.stdout.readline(), timeout=10.0)
            if not header:
                return None

            content_length = 0
            while header and header.strip():
                line = header.decode("utf-8").strip()
                if line.startswith("Content-Length:"):
                    content_length = int(line.split(":")[1].strip())
                header = await asyncio.wait_for(self._proc.stdout.readline(), timeout=5.0)

            if content_length == 0:
                return None

            body = await asyncio.wait_for(
                self._proc.stdout.read(content_length), timeout=10.0
            )
            return json.loads(body.decode("utf-8"))
        except (asyncio.TimeoutError, json.JSONDecodeError, OSError) as e:
            logger.warning("LSP read failed: %s", e)
            return None

    async def definition(self, file_path: str, line: int, character: int) -> dict | None:
        return await self._send_request(
            "textDocument/definition",
            {
                "textDocument": {"uri": Path(file_path).as_uri()},
                "position": {"line": line - 1, "character": character - 1},
            },
        )

    async def references(self, file_path: str, line: int, character: int) -> dict | None:
        return await self._send_request(
            "textDocument/references",
            {
                "textDocument": {"uri": Path(file_path).as_uri()},
                "position": {"line": line - 1, "character": character - 1},
                "context": {"includeDeclaration": True},
            },
        )

    async def hover(self, file_path: str, line: int, character: int) -> dict | None:
        return await self._send_request(
            "textDocument/hover",
            {
                "textDocument": {"uri": Path(file_path).as_uri()},
                "position": {"line": line - 1, "character": character - 1},
            },
        )

    async def diagnostics(self, file_path: str) -> list[dict]:
        result = await self._send_request(
            "textDocument/publishDiagnostics",
            {"textDocument": {"uri": Path(file_path).as_uri()}},
        )
        return result.get("params", {}).get("diagnostics", []) if result else []

    async def symbol(self, query: str) -> dict | None:
        return await self._send_request(
            "workspace/symbol", {"query": query}
        )

    async def shutdown(self) -> None:
        if self._proc and self._initialized:
            await self._send_request("shutdown", {})
            await self._send_notification("exit", {})
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except (asyncio.TimeoutError, OSError):
                try:
                    self._proc.kill()
                except OSError:
                    pass
            self._initialized = False


def _get_language_for_file(file_path: str) -> str:
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
    }
    ext = Path(file_path).suffix.lower()
    return ext_map.get(ext, "")


def _get_lsp_command_for_language(language: str) -> list[str] | None:
    commands: dict[str, list[str]] = {
        "python": [sys.executable, "-m", "pylsp"],
        "javascript": ["typescript-language-server", "--stdio"],
        "typescript": ["typescript-language-server", "--stdio"],
    }
    return commands.get(language)


def _parse_location(location: dict) -> str:
    uri = location.get("uri", "")
    range_data = location.get("range", {})
    start = range_data.get("start", {})
    path = uri.replace("file:///", "").replace("file://", "")
    if sys.platform == "win32" and path:
        path = uri.replace("file:///", "").replace("/", "\\")
        if not path:
            path = uri.replace("file://", "")
    line = start.get("line", 0) + 1
    char = start.get("character", 0) + 1
    return f"{path}:{line}:{char}"


class LSPTool(Tool):
    name = "LSP"
    description = "LSP 语言服务集成。支持定义跳转、引用查找、悬停信息、诊断获取和符号搜索。"
    input_schema = LSPInput
    is_readonly = True
    is_lazy = True

    def is_available(self) -> bool:
        return True

    async def call(self, input: LSPInput, context: Any) -> ToolResult:
        operation = input.operation.lower()

        if operation == "diagnostics":
            return await self._diagnostics(input, context)
        if operation == "symbol":
            return await self._symbol_search(input, context)

        if not input.file_path:
            return ToolResult(output="需要指定 file_path", is_error=True)
        if input.line is None or input.character is None:
            return ToolResult(output="需要指定 line 和 character", is_error=True)

        language = input.language or _get_language_for_file(input.file_path)
        if not language:
            return ToolResult(output="无法识别文件语言，请通过 language 参数指定", is_error=True)

        client = await _get_or_create_client(language, str(context.cwd))
        if client is None:
            return ToolResult(output=f"无法启动 LSP 服务器（语言: {language}）。请确保已安装对应的语言服务器。", is_error=True)

        handlers = {
            "definition": client.definition,
            "references": client.references,
            "hover": client.hover,
        }
        handler = handlers.get(operation)
        if handler is None:
            return ToolResult(
                output=f"未知操作: {operation}。支持: definition, references, diagnostics, symbol, hover",
                is_error=True,
            )

        response = await handler(input.file_path, input.line, input.character)
        if response is None:
            return ToolResult(output="LSP 请求失败", is_error=True)

        return _format_response(operation, response)

    async def _diagnostics(self, input: LSPInput, context: Any) -> ToolResult:
        if not input.file_path:
            return ToolResult(output="需要指定 file_path", is_error=True)

        language = input.language or _get_language_for_file(input.file_path)
        if not language:
            return ToolResult(output="无法识别文件语言", is_error=True)

        client = await _get_or_create_client(language, str(context.cwd))
        if client is None:
            return ToolResult(output=f"无法启动 LSP 服务器（语言: {language}）", is_error=True)

        response = await client._send_request(
            "textDocument/diagnostic",
            {"textDocument": {"uri": Path(input.file_path).as_uri()}},
        )

        if response is None:
            items = []
        else:
            result = response.get("result", {})
            if isinstance(result, dict):
                items = result.get("items", [])
            elif isinstance(result, list):
                items = result
            else:
                items = []

        if not items:
            return ToolResult(output=f"无诊断信息: {input.file_path}")

        parts = [f"诊断 ({len(items)} 项):"]
        for item in items[:20]:
            severity_map = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}
            severity = severity_map.get(item.get("severity", 3), "Unknown")
            msg = item.get("message", "")
            rng = item.get("range", {})
            start = rng.get("start", {})
            line = start.get("line", 0) + 1
            parts.append(f"  L{line} [{severity}]: {msg}")

        return ToolResult(output="\n".join(parts))

    async def _symbol_search(self, input: LSPInput, context: Any) -> ToolResult:
        if not input.query:
            return ToolResult(output="需要指定 query 参数", is_error=True)

        language = input.language or "python"
        client = await _get_or_create_client(language, str(context.cwd))
        if client is None:
            return ToolResult(output=f"无法启动 LSP 服务器（语言: {language}）", is_error=True)

        response = await client._send_request(
            "workspace/symbol",
            {"query": input.query},
        )

        if response is None:
            return ToolResult(output="符号搜索失败", is_error=True)

        symbols = response.get("result") or []
        if not symbols:
            return ToolResult(output=f"未找到符号: {input.query}")

        parts = [f"符号搜索结果 ({len(symbols)} 个):"]
        kind_map = {
            1: "File", 2: "Module", 3: "Namespace", 4: "Package",
            5: "Class", 6: "Method", 7: "Property", 8: "Field",
            9: "Constructor", 10: "Enum", 11: "Interface", 12: "Function",
            13: "Variable", 14: "Constant", 15: "String", 16: "Number",
            17: "Boolean", 18: "Array", 19: "Object", 20: "Key",
            21: "Null", 22: "EnumMember", 23: "Struct", 24: "Event",
            25: "Operator", 26: "TypeParameter",
        }
        for sym in symbols[:20]:
            name = sym.get("name", "")
            kind = kind_map.get(sym.get("kind", 0), "Unknown")
            loc = sym.get("location", {})
            location_str = _parse_location(loc) if isinstance(loc, dict) else ""
            parts.append(f"  {name} [{kind}] {location_str}")

        return ToolResult(output="\n".join(parts))


async def _get_or_create_client(language: str, cwd: str) -> LSPClient | None:
    if language in _lsp_clients:
        client = _lsp_clients[language]
        if client._initialized:
            return client

    command = _get_lsp_command_for_language(language)
    if command is None:
        return None

    client = LSPClient(command, cwd)
    if not await client.start():
        return None

    _lsp_clients[language] = client
    return client


def _format_response(operation: str, response: dict) -> ToolResult:
    result = response.get("result")

    if result is None:
        return ToolResult(output=f"{operation}: 无结果")

    if operation == "definition":
        if isinstance(result, list):
            if not result:
                return ToolResult(output="定义跳转: 未找到定义")
            locations = result
        elif isinstance(result, dict):
            locations = [result]
        else:
            return ToolResult(output=f"定义跳转: 未知响应格式")

        parts = ["定义跳转:"]
        for loc in locations[:10]:
            if isinstance(loc, dict):
                parts.append(f"  {_parse_location(loc)}")
        return ToolResult(output="\n".join(parts))

    if operation == "references":
        refs = result if isinstance(result, list) else []
        if not refs:
            return ToolResult(output="引用查找: 未找到引用")
        parts = [f"引用查找 ({len(refs)} 个):"]
        for ref in refs[:20]:
            if isinstance(ref, dict):
                parts.append(f"  {_parse_location(ref)}")
        return ToolResult(output="\n".join(parts))

    if operation == "hover":
        contents = []
        if isinstance(result, dict):
            hover_content = result.get("contents", "")
            if isinstance(hover_content, dict):
                value = hover_content.get("value", "")
                if value:
                    contents.append(value)
            elif isinstance(hover_content, str) and hover_content:
                contents.append(hover_content)
            elif isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        c = item.get("value", "") or str(item)
                        if c:
                            contents.append(c[:500])
                    else:
                        contents.append(str(item)[:500])
        if not contents:
            return ToolResult(output="悬停信息: 无内容")
        return ToolResult(output="\n---\n".join(contents[:5]))

    return ToolResult(output=str(result)[:500])
