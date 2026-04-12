from __future__ import annotations

from typing import AsyncGenerator

from rich.console import Console
from rich.markdown import Markdown

from src.api_client import StreamEvent

console = Console()

MAX_ARG_DISPLAY = 100


def _truncate_args(args_str: str) -> str:
    if len(args_str) > MAX_ARG_DISPLAY:
        return args_str[:MAX_ARG_DISPLAY] + "..."
    return args_str


async def render_stream(events: AsyncGenerator[StreamEvent, None]) -> str:
    reasoning_text = ""
    answer_text = ""
    in_reasoning = False
    reasoning_printed = False

    async for event in events:
        if event.type == "reasoning_delta":
            in_reasoning = True
            reasoning_text += event.data.get("text", "")
            if not reasoning_printed:
                reasoning_printed = True
                console.print("🧠 思考中...", style="dim")

        elif event.type == "text_delta":
            if in_reasoning:
                in_reasoning = False
                answer_text = ""
            answer_text += event.data.get("text", "")

        elif event.type == "checkpoint":
            console.print(f"📌 checkpoint #{event.data['index']}", style="bold cyan")

        elif event.type == "tool_call_summary":
            args_preview = _truncate_args(event.data.get("arguments", ""))
            console.print(f"🔧 调用工具: {event.data['name']}  {args_preview}", style="bold yellow")

        elif event.type == "message_stop":
            pass

    if answer_text:
        console.print(Markdown(answer_text))

    return answer_text
