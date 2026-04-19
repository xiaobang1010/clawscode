from __future__ import annotations

import asyncio
import base64
import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class CDPResponse:
    id: int
    result: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None


@dataclass
class Viewport:
    width: int = 1280
    height: int = 720


class BrowserService:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 9222,
        viewport: Viewport | None = None,
    ):
        self._host = host
        self._port = port
        self._viewport = viewport or Viewport()
        self._ws = None
        self._msg_id = 0
        self._pending: dict[int, asyncio.Future[CDPResponse]] = {}
        self._reader_task: asyncio.Task | None = None
        self._process: subprocess.Popen | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None

    @property
    def http_base(self) -> str:
        return f"http://{self._host}:{self._port}"

    async def launch(self, executable: str | None = None) -> None:
        chrome = executable or _find_chrome()
        if not chrome:
            raise BrowserError(
                "未找到 Chrome/Chromium 浏览器。请安装 Chrome 或指定浏览器路径。"
            )
        self._process = subprocess.Popen(
            [
                chrome,
                f"--remote-debugging-port={self._port}",
                f"--window-size={self._viewport.width},{self._viewport.height}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-client-side-phishing-detection",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-hang-monitor",
                "--disable-popup-blocking",
                "--disable-prompt-on-repost",
                "--disable-sync",
                "--metrics-recording-only",
                "--safebrowsing-disable-auto-update",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{self.http_base}/json/version", timeout=2.0)
                    if resp.status_code == 200:
                        return
            except (httpx.ConnectError, httpx.TimeoutException):
                pass
            await asyncio.sleep(0.2)
        raise BrowserError("浏览器启动超时，无法连接到 CDP 端口")

    async def connect(self) -> None:
        if self.is_connected:
            return
        ws_url = await self._get_ws_url()
        try:
            import websockets

            self._ws = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)
        except ImportError:
            raise BrowserError("需要安装 websockets 库：pip install websockets")
        except Exception as e:
            raise BrowserError(f"WebSocket 连接失败: {e}")
        self._connected = True
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def disconnect(self) -> None:
        self._connected = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    async def shutdown(self) -> None:
        await self.disconnect()
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    async def send_command(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.is_connected:
            raise BrowserError("未连接到浏览器，请先调用 connect()")
        self._msg_id += 1
        msg_id = self._msg_id
        message = {"id": msg_id, "method": method, "params": params or {}}
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[CDPResponse] = loop.create_future()
        self._pending[msg_id] = fut
        try:
            await self._ws.send(json.dumps(message))
        except Exception as e:
            self._pending.pop(msg_id, None)
            raise BrowserError(f"发送 CDP 命令失败: {e}")
        try:
            resp = await asyncio.wait_for(fut, timeout=30.0)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise BrowserError(f"CDP 命令超时: {method}")
        if resp.error:
            raise BrowserError(f"CDP 错误: {resp.error}")
        return resp.result

    async def screenshot(self, format: str = "png", quality: int | None = None) -> str:
        params: dict[str, Any] = {"format": format}
        if quality is not None and format == "jpeg":
            params["quality"] = quality
        result = await self.send_command("Page.captureScreenshot", params)
        return result.get("data", "")

    async def mouse_event(
        self,
        type: str,
        x: int,
        y: int,
        button: str = "none",
        click_count: int = 1,
    ) -> None:
        await self.send_command(
            "Input.dispatchMouseEvent",
            {
                "type": type,
                "x": x,
                "y": y,
                "button": button,
                "clickCount": click_count,
            },
        )

    async def mouse_click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        count = 2 if double else 1
        await self.mouse_event("mousePressed", x, y, button=button, click_count=count)
        await self.mouse_event("mouseReleased", x, y, button=button, click_count=count)

    async def mouse_move(self, x: int, y: int) -> None:
        await self.mouse_event("mouseMoved", x, y)

    async def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        await self.mouse_event("mousePressed", start_x, start_y, button="left")
        steps = 10
        for i in range(1, steps + 1):
            x = start_x + (end_x - start_x) * i // steps
            y = start_y + (end_y - start_y) * i // steps
            await self.mouse_move(x, y)
            await asyncio.sleep(0.02)
        await self.mouse_event("mouseReleased", end_x, end_y, button="left")

    async def scroll(self, x: int, y: int, delta_x: int = 0, delta_y: int = 0) -> None:
        await self.send_command(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseWheel",
                "x": x,
                "y": y,
                "deltaX": delta_x,
                "deltaY": delta_y,
            },
        )

    async def key_event(
        self,
        type: str,
        key: str,
        code: str = "",
        modifiers: int = 0,
        text: str | None = None,
    ) -> None:
        params: dict[str, Any] = {
            "type": type,
            "key": key,
            "code": code or _key_to_code(key),
            "modifiers": modifiers,
        }
        if text:
            params["text"] = text
            params["unmodifiedText"] = text
        await self.send_command("Input.dispatchKeyEvent", params)

    async def key_press(self, key: str, modifiers: int = 0) -> None:
        await self.key_event("keyDown", key, modifiers=modifiers)
        await self.key_event("keyUp", key, modifiers=modifiers)

    async def type_text(self, text: str, modifiers: int = 0) -> None:
        for char in text:
            await self.key_event("keyDown", char, text=char, modifiers=modifiers)
            await self.key_event("keyUp", char, modifiers=modifiers)
            await asyncio.sleep(0.01)

    async def navigate(self, url: str, wait: bool = True) -> dict[str, Any]:
        if not url.startswith(("http://", "https://", "file://")):
            url = "https://" + url
        result = await self.send_command("Page.navigate", {"url": url})
        if wait:
            await asyncio.sleep(1.0)
        return result

    async def get_page_info(self) -> dict[str, Any]:
        result = await self.send_command(
            "Runtime.evaluate",
            {
                "expression": "JSON.stringify({url: location.href, title: document.title})",
                "returnByValue": True,
            },
        )
        try:
            value = result["result"]["value"]
            return json.loads(value)
        except (KeyError, json.JSONDecodeError):
            return {"url": "", "title": ""}

    async def get_viewport_size(self) -> dict[str, int]:
        result = await self.send_command(
            "Runtime.evaluate",
            {
                "expression": "JSON.stringify({width: window.innerWidth, height: window.innerHeight})",
                "returnByValue": True,
            },
        )
        try:
            value = result["result"]["value"]
            return json.loads(value)
        except (KeyError, json.JSONDecodeError):
            return {"width": self._viewport.width, "height": self._viewport.height}

    async def set_viewport(self, width: int, height: int) -> None:
        await self.send_command(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        )
        await self.send_command(
            "Emulation.setVisibleSize",
            {"width": width, "height": height},
        )
        self._viewport = Viewport(width=width, height=height)

    async def execute_js(self, expression: str) -> Any:
        result = await self.send_command(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True},
        )
        if "exceptionDetails" in result:
            desc = result["exceptionDetails"].get("text", "未知错误")
            raise BrowserError(f"JavaScript 执行错误: {desc}")
        return result.get("result", {}).get("value")

    async def _get_ws_url(self) -> str:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.http_base}/json", timeout=5.0)
                targets = resp.json()
                if targets:
                    return targets[0].get("webSocketDebuggerUrl", "")
        except Exception as e:
            raise BrowserError(f"获取 CDP WebSocket URL 失败: {e}")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.http_base}/json/version", timeout=5.0)
                version_info = resp.json()
                return version_info.get("webSocketDebuggerUrl", "")
        except Exception:
            pass
        raise BrowserError("未找到可用的 CDP 目标")

    async def _reader_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg_id = msg.get("id")
                if msg_id and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        resp = CDPResponse(
                            id=msg_id,
                            result=msg.get("result", {}),
                            error=msg.get("error"),
                        )
                        fut.set_result(resp)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            self._connected = False


class BrowserError(Exception):
    pass


_KEY_CODE_MAP: dict[str, str] = {
    "Enter": "Enter",
    "Tab": "Tab",
    "Escape": "Escape",
    "Backspace": "Backspace",
    "Delete": "Delete",
    "ArrowUp": "ArrowUp",
    "ArrowDown": "ArrowDown",
    "ArrowLeft": "ArrowLeft",
    "ArrowRight": "ArrowRight",
    "Home": "Home",
    "End": "End",
    "PageUp": "PageUp",
    "PageDown": "PageDown",
    " ": "Space",
    "Control": "ControlLeft",
    "Alt": "AltLeft",
    "Shift": "ShiftLeft",
    "Meta": "MetaLeft",
    "F1": "F1",
    "F2": "F2",
    "F3": "F3",
    "F4": "F4",
    "F5": "F5",
    "F6": "F6",
    "F7": "F7",
    "F8": "F8",
    "F9": "F9",
    "F10": "F10",
    "F11": "F11",
    "F12": "F12",
}


def _key_to_code(key: str) -> str:
    return _KEY_CODE_MAP.get(key, f"Key{key.upper()}" if len(key) == 1 else key)


def _find_chrome() -> str | None:
    if sys.platform == "win32":
        candidates = [
            Path(os) / "Google" / "Chrome" / "Application" / "chrome.exe"
            for os in [
                os.environ.get("PROGRAMFILES", ""),
                os.environ.get("PROGRAMFILES(X86)", ""),
                os.environ.get("LOCALAPPDATA", ""),
            ]
            if os
        ]
        candidates.extend([
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            for _ in [1] if os.environ.get("PROGRAMFILES", "")
        ])
    elif sys.platform == "darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
    else:
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/microsoft-edge"),
        ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


import os

_browser_service: BrowserService | None = None


def get_browser_service() -> BrowserService:
    global _browser_service
    if _browser_service is None:
        _browser_service = BrowserService()
    return _browser_service


def set_browser_service(service: BrowserService) -> None:
    global _browser_service
    _browser_service = service
