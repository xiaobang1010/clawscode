from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult
from src.services.browser import BrowserService, BrowserError, get_browser_service


async def _ensure_connected(service: BrowserService) -> None:
    if not service.is_connected:
        await service.connect()


class BrowserScreenshotInput(BaseModel):
    format: str = Field(
        default="png",
        description="截图格式：png 或 jpeg",
    )
    quality: int | None = Field(
        default=None,
        description="JPEG 质量（1-100），仅 format=jpeg 时有效",
    )


class BrowserScreenshotTool(Tool):
    name = "BrowserScreenshot"
    description = "截取浏览器当前页面的屏幕截图，返回 Base64 编码的图片数据"
    input_schema = BrowserScreenshotInput
    user_facing_name = "浏览器截图"
    is_readonly = True
    is_lazy = True

    def is_available(self) -> bool:
        try:
            import websockets  # noqa: F401
            return True
        except ImportError:
            return False

    async def call(self, input: BrowserScreenshotInput, context: Any) -> ToolResult:
        service = get_browser_service()
        try:
            await _ensure_connected(service)
            data = await service.screenshot(format=input.format, quality=input.quality)
            info = await service.get_page_info()
            return ToolResult(
                output=f"截图成功\n"
                       f"页面: {info.get('title', '未知')}\n"
                       f"URL: {info.get('url', '未知')}\n"
                       f"格式: {input.format}\n"
                       f"Base64 数据长度: {len(data)} 字符\n"
                       f"data:image/{input.format};base64,{data}"
            )
        except BrowserError as e:
            return ToolResult(output=str(e), is_error=True)
        except Exception as e:
            return ToolResult(output=f"截图失败: {e}", is_error=True)


class BrowserMouseClickInput(BaseModel):
    x: int = Field(description="点击的 X 坐标（像素）")
    y: int = Field(description="点击的 Y 坐标（像素）")
    button: str = Field(
        default="left",
        description="鼠标按钮：left、right、middle",
    )
    double: bool = Field(
        default=False,
        description="是否双击",
    )


class BrowserMouseClickTool(Tool):
    name = "BrowserMouseClick"
    description = "在浏览器页面的指定坐标位置点击鼠标"
    input_schema = BrowserMouseClickInput
    user_facing_name = "浏览器鼠标点击"
    is_readonly = False
    is_lazy = True

    def is_available(self) -> bool:
        try:
            import websockets  # noqa: F401
            return True
        except ImportError:
            return False

    async def call(self, input: BrowserMouseClickInput, context: Any) -> ToolResult:
        service = get_browser_service()
        try:
            await _ensure_connected(service)
            await service.mouse_click(
                x=input.x,
                y=input.y,
                button=input.button,
                double=input.double,
            )
            action = "双击" if input.double else "点击"
            return ToolResult(output=f"已{action}坐标 ({input.x}, {input.y})，按钮: {input.button}")
        except BrowserError as e:
            return ToolResult(output=str(e), is_error=True)
        except Exception as e:
            return ToolResult(output=f"鼠标点击失败: {e}", is_error=True)


class BrowserMouseMoveInput(BaseModel):
    x: int = Field(description="移动目标的 X 坐标（像素）")
    y: int = Field(description="移动目标的 Y 坐标（像素）")


class BrowserMouseMoveTool(Tool):
    name = "BrowserMouseMove"
    description = "移动浏览器中的鼠标指针到指定坐标"
    input_schema = BrowserMouseMoveInput
    user_facing_name = "浏览器鼠标移动"
    is_readonly = True
    is_lazy = True

    def is_available(self) -> bool:
        try:
            import websockets  # noqa: F401
            return True
        except ImportError:
            return False

    async def call(self, input: BrowserMouseMoveInput, context: Any) -> ToolResult:
        service = get_browser_service()
        try:
            await _ensure_connected(service)
            await service.mouse_move(x=input.x, y=input.y)
            return ToolResult(output=f"鼠标已移动到 ({input.x}, {input.y})")
        except BrowserError as e:
            return ToolResult(output=str(e), is_error=True)
        except Exception as e:
            return ToolResult(output=f"鼠标移动失败: {e}", is_error=True)


class BrowserDragInput(BaseModel):
    start_x: int = Field(description="起始 X 坐标")
    start_y: int = Field(description="起始 Y 坐标")
    end_x: int = Field(description="目标 X 坐标")
    end_y: int = Field(description="目标 Y 坐标")


class BrowserDragTool(Tool):
    name = "BrowserDrag"
    description = "在浏览器中执行拖拽操作（从起点拖拽到终点）"
    input_schema = BrowserDragInput
    user_facing_name = "浏览器拖拽"
    is_readonly = False
    is_lazy = True

    def is_available(self) -> bool:
        try:
            import websockets  # noqa: F401
            return True
        except ImportError:
            return False

    async def call(self, input: BrowserDragInput, context: Any) -> ToolResult:
        service = get_browser_service()
        try:
            await _ensure_connected(service)
            await service.mouse_drag(
                start_x=input.start_x,
                start_y=input.start_y,
                end_x=input.end_x,
                end_y=input.end_y,
            )
            return ToolResult(
                output=f"拖拽完成: ({input.start_x}, {input.start_y}) -> ({input.end_x}, {input.end_y})"
            )
        except BrowserError as e:
            return ToolResult(output=str(e), is_error=True)
        except Exception as e:
            return ToolResult(output=f"拖拽失败: {e}", is_error=True)


class BrowserScrollInput(BaseModel):
    x: int = Field(default=0, description="滚动位置的 X 坐标")
    y: int = Field(default=0, description="滚动位置的 Y 坐标")
    delta_x: int = Field(default=0, description="水平滚动量（正数向右，负数向左）")
    delta_y: int = Field(default=300, description="垂直滚动量（正数向下，负数向上）")


class BrowserScrollTool(Tool):
    name = "BrowserScroll"
    description = "在浏览器中滚动页面"
    input_schema = BrowserScrollInput
    user_facing_name = "浏览器滚动"
    is_readonly = True
    is_lazy = True

    def is_available(self) -> bool:
        try:
            import websockets  # noqa: F401
            return True
        except ImportError:
            return False

    async def call(self, input: BrowserScrollInput, context: Any) -> ToolResult:
        service = get_browser_service()
        try:
            await _ensure_connected(service)
            await service.scroll(x=input.x, y=input.y, delta_x=input.delta_x, delta_y=input.delta_y)
            direction = ""
            if input.delta_y > 0:
                direction += "向下"
            elif input.delta_y < 0:
                direction += "向上"
            if input.delta_x > 0:
                direction += "向右"
            elif input.delta_x < 0:
                direction += "向左"
            return ToolResult(output=f"已滚动{direction}，delta=({input.delta_x}, {input.delta_y})")
        except BrowserError as e:
            return ToolResult(output=str(e), is_error=True)
        except Exception as e:
            return ToolResult(output=f"滚动失败: {e}", is_error=True)


class BrowserKeyboardInput(BaseModel):
    action: str = Field(
        description="操作类型：type（输入文本）、press（按下按键）、shortcut（组合快捷键，如 Ctrl+C）",
    )
    text: str | None = Field(
        default=None,
        description="当 action=type 时，要输入的文本内容",
    )
    key: str | None = Field(
        default=None,
        description="当 action=press 时，要按下的按键（如 Enter、Tab、Escape、ArrowDown）",
    )
    shortcut: str | None = Field(
        default=None,
        description='当 action=shortcut 时，组合快捷键（如 "Ctrl+C"、"Ctrl+Shift+I"）',
    )


class BrowserKeyboardTool(Tool):
    name = "BrowserKeyboard"
    description = "在浏览器中执行键盘操作：输入文本、按下按键、或发送快捷键组合"
    input_schema = BrowserKeyboardInput
    user_facing_name = "浏览器键盘"
    is_readonly = False
    is_lazy = True

    def is_available(self) -> bool:
        try:
            import websockets  # noqa: F401
            return True
        except ImportError:
            return False

    async def call(self, input: BrowserKeyboardInput, context: Any) -> ToolResult:
        service = get_browser_service()
        try:
            await _ensure_connected(service)
            if input.action == "type":
                if not input.text:
                    return ToolResult(output="action=type 需要提供 text 参数", is_error=True)
                await service.type_text(input.text)
                return ToolResult(output=f"已输入文本: {input.text[:50]}{'...' if len(input.text) > 50 else ''}")
            elif input.action == "press":
                if not input.key:
                    return ToolResult(output="action=press 需要提供 key 参数", is_error=True)
                await service.key_press(input.key)
                return ToolResult(output=f"已按下按键: {input.key}")
            elif input.action == "shortcut":
                if not input.shortcut:
                    return ToolResult(output="action=shortcut 需要提供 shortcut 参数", is_error=True)
                keys, modifier = _parse_shortcut(input.shortcut)
                for key in keys:
                    await service.key_press(key, modifiers=modifier)
                return ToolResult(output=f"已执行快捷键: {input.shortcut}")
            else:
                return ToolResult(
                    output=f"未知操作类型: {input.action}，支持: type、press、shortcut",
                    is_error=True,
                )
        except BrowserError as e:
            return ToolResult(output=str(e), is_error=True)
        except Exception as e:
            return ToolResult(output=f"键盘操作失败: {e}", is_error=True)


class BrowserNavigateInput(BaseModel):
    url: str = Field(description="要导航到的 URL")
    wait: bool = Field(default=True, description="是否等待页面加载完成")


class BrowserNavigateTool(Tool):
    name = "BrowserNavigate"
    description = "导航浏览器到指定 URL"
    input_schema = BrowserNavigateInput
    user_facing_name = "浏览器导航"
    is_readonly = False
    is_lazy = True

    def is_available(self) -> bool:
        try:
            import websockets  # noqa: F401
            return True
        except ImportError:
            return False

    async def call(self, input: BrowserNavigateInput, context: Any) -> ToolResult:
        service = get_browser_service()
        try:
            await _ensure_connected(service)
            result = await service.navigate(url=input.url, wait=input.wait)
            info = await service.get_page_info()
            return ToolResult(
                output=f"已导航到: {info.get('url', input.url)}\n"
                       f"页面标题: {info.get('title', '未知')}"
            )
        except BrowserError as e:
            return ToolResult(output=str(e), is_error=True)
        except Exception as e:
            return ToolResult(output=f"导航失败: {e}", is_error=True)


class BrowserLaunchInput(BaseModel):
    executable: str | None = Field(
        default=None,
        description="Chrome/Chromium 可执行文件路径（可选，自动检测）",
    )
    port: int = Field(default=9222, description="CDP 远程调试端口")
    width: int = Field(default=1280, description="浏览器窗口宽度")
    height: int = Field(default=720, description="浏览器窗口高度")


class BrowserLaunchTool(Tool):
    name = "BrowserLaunch"
    description = "启动浏览器并连接 CDP（Chrome DevTools Protocol），后续可进行截图、点击、键盘等操作"
    input_schema = BrowserLaunchInput
    user_facing_name = "启动浏览器"
    is_readonly = False
    is_lazy = True

    def is_available(self) -> bool:
        try:
            import websockets  # noqa: F401
            return True
        except ImportError:
            return False

    async def call(self, input: BrowserLaunchInput, context: Any) -> ToolResult:
        from src.services.browser import BrowserService, set_browser_service, Viewport
        service = BrowserService(
            port=input.port,
            viewport=Viewport(width=input.width, height=input.height),
        )
        try:
            await service.launch(executable=input.executable)
            await service.connect()
            set_browser_service(service)
            return ToolResult(
                output=f"浏览器已启动并连接\n"
                       f"CDP 端口: {input.port}\n"
                       f"窗口大小: {input.width}x{input.height}"
            )
        except BrowserError as e:
            return ToolResult(output=str(e), is_error=True)
        except Exception as e:
            return ToolResult(output=f"启动浏览器失败: {e}", is_error=True)


class BrowserConnectInput(BaseModel):
    host: str = Field(default="localhost", description="CDP 主机地址")
    port: int = Field(default=9222, description="CDP 端口")


class BrowserConnectTool(Tool):
    name = "BrowserConnect"
    description = "连接到已运行的浏览器 CDP 端口（浏览器需已启用远程调试）"
    input_schema = BrowserConnectInput
    user_facing_name = "连接浏览器"
    is_readonly = True
    is_lazy = True

    def is_available(self) -> bool:
        try:
            import websockets  # noqa: F401
            return True
        except ImportError:
            return False

    async def call(self, input: BrowserConnectInput, context: Any) -> ToolResult:
        from src.services.browser import BrowserService, set_browser_service
        service = BrowserService(host=input.host, port=input.port)
        try:
            await service.connect()
            set_browser_service(service)
            info = await service.get_page_info()
            return ToolResult(
                output=f"已连接到浏览器 CDP ({input.host}:{input.port})\n"
                       f"当前页面: {info.get('title', '未知')}\n"
                       f"URL: {info.get('url', '未知')}"
            )
        except BrowserError as e:
            return ToolResult(output=str(e), is_error=True)
        except Exception as e:
            return ToolResult(output=f"连接失败: {e}", is_error=True)


class BrowserShutdownInput(BaseModel):
    pass


class BrowserShutdownTool(Tool):
    name = "BrowserShutdown"
    description = "关闭浏览器并断开 CDP 连接"
    input_schema = BrowserShutdownInput
    user_facing_name = "关闭浏览器"
    is_readonly = False
    is_lazy = True

    def is_available(self) -> bool:
        try:
            import websockets  # noqa: F401
            return True
        except ImportError:
            return False

    async def call(self, input: BrowserShutdownInput, context: Any) -> ToolResult:
        service = get_browser_service()
        try:
            await service.shutdown()
            return ToolResult(output="浏览器已关闭")
        except Exception as e:
            return ToolResult(output=f"关闭浏览器失败: {e}", is_error=True)


_MODIFIER_MAP: dict[str, int] = {
    "Alt": 1,
    "AltGr": 1,
    "Control": 2,
    "Ctrl": 2,
    "Meta": 4,
    "Shift": 8,
}


def _parse_shortcut(shortcut: str) -> tuple[list[str], int]:
    parts = [p.strip() for p in shortcut.split("+")]
    modifiers = 0
    keys: list[str] = []
    for part in parts:
        if part in _MODIFIER_MAP:
            modifiers |= _MODIFIER_MAP[part]
        else:
            keys.append(part)
    if not keys:
        keys = [parts[-1]]
    return keys, modifiers
