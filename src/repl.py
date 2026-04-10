from __future__ import annotations

from typing import AsyncGenerator

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from src.api_client import StreamEvent

console = Console()


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
                answer_text += event.data.get("text", "")
                live.update(Markdown(answer_text))

            elif event.type == "tool_calls":
                live.update(f"\n🔧 调用工具: {event.data['name']}")

            elif event.type == "message_stop":
                live.update(Markdown(answer_text))

    return answer_text
