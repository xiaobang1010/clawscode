from __future__ import annotations

from typing import Any, Callable, Awaitable


class CommandRegistry:
    def __init__(self) -> None:
        self.commands: dict[str, Callable[..., Awaitable[str | None]]] = {}

    def register(self, name: str, handler: Callable[..., Awaitable[str | None]]) -> None:
        self.commands[name] = handler

    def is_command(self, text: str) -> bool:
        return text.startswith("/")

    async def execute(self, text: str, context: Any) -> str | None:
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        handler = self.commands.get(cmd)
        if handler:
            return await handler(args, context)
        return f"未知命令: /{cmd}"


def register_commands(registry: CommandRegistry) -> None:
    async def help_command(args: str, context: Any) -> str:
        lines = ["可用命令："]
        for name in sorted(registry.commands):
            lines.append(f"  /{name}")
        return "\n".join(lines)

    async def clear_command(args: str, context: Any) -> str | None:
        if hasattr(context, "messages"):
            context.messages.clear()
        return "对话历史已清除"

    async def config_command(args: str, context: Any) -> str:
        if hasattr(context, "settings"):
            s = context.settings
            return f"当前配置：\n  model: {s.model}\n  base_url: {s.base_url}\n  max_tokens: {s.max_tokens}"
        return "无配置信息"

    async def compact_command(args: str, context: Any) -> str:
        return "手动压缩已触发"

    async def model_command(args: str, context: Any) -> str:
        if args and hasattr(context, "settings"):
            context.settings.model = args
            return f"模型已切换为: {args}"
        if hasattr(context, "settings"):
            return f"当前模型: {context.settings.model}"
        return "无模型信息"

    registry.register("help", help_command)
    registry.register("clear", clear_command)
    registry.register("config", config_command)
    registry.register("compact", compact_command)
    registry.register("model", model_command)
