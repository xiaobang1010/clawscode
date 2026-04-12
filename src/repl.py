from __future__ import annotations

from typing import AsyncGenerator

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

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

    with Live(console=console, refresh_per_second=10) as live:
        async for event in events:
            if event.type == "reasoning_delta":
                in_reasoning = True
                reasoning_text += event.data.get("text", "")
                display = Text()
                if reasoning_text:
                    display.append("🧠 思考中...\n", style="dim italic")
                    display.append(reasoning_text, style="dim")
                live.update(display)

            elif event.type == "text_delta":
                if in_reasoning:
                    in_reasoning = False
                    answer_text = ""
                    live.update(Text())
                answer_text += event.data.get("text", "")
                live.update(Markdown(answer_text))

            elif event.type == "checkpoint":
                live.update(Text(f"\n📌 checkpoint #{event.data['index']}", style="bold cyan"))

            elif event.type == "tool_calls":
                args_preview = _truncate_args(event.data.get("arguments", ""))
                live.update(Text(f"\n🔧 调用工具: {event.data['name']}", style="bold yellow"), Text(f"  {args_preview}", style="dim"))

            elif event.type == "message_stop":
                live.update(Markdown(answer_text))

    return answer_text
