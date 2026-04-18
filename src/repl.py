from __future__ import annotations

from typing import AsyncGenerator

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from src.api_client import StreamEvent

console = Console()

MAX_ARG_DISPLAY = 100


def _truncate_args(args_str: str) -> str:
    if len(args_str) > MAX_ARG_DISPLAY:
        return args_str[:MAX_ARG_DISPLAY] + "..."
    return args_str


async def render_stream(
    events: AsyncGenerator[StreamEvent, None], cost_tracker=None
) -> str:
    reasoning_text = ""
    answer_text = ""
    in_reasoning = False
    reasoning_printed = False
    total_input_tokens = 0
    total_output_tokens = 0

    with console.status("思考中...") as status:
        async for event in events:
            if event.type == "reasoning_delta":
                in_reasoning = True
                reasoning_text += event.data.get("text", "")
                if not reasoning_printed:
                    reasoning_printed = True
                status.update(f"🧠 思考中... ({len(reasoning_text)} chars)")

            elif event.type == "text_delta":
                if in_reasoning:
                    in_reasoning = False
                    answer_text = ""
                answer_text += event.data.get("text", "")
                status.update("📝 生成回复...")

            elif event.type == "checkpoint":
                console.print(
                    f"📌 checkpoint #{event.data['index']}", style="bold cyan"
                )

            elif event.type == "tool_call_summary":
                args_preview = _truncate_args(event.data.get("arguments", ""))
                console.print(
                    f"🔧 调用工具: {event.data['name']}  {args_preview}",
                    style="bold yellow",
                )
                status.update("🔧 等待工具结果...")

            elif event.type == "usage":
                total_input_tokens += event.data.get("input_tokens", 0)
                total_output_tokens += event.data.get("output_tokens", 0)
                duration = event.data.get("duration_ms", 0)
                if duration > 0:
                    console.print(
                        f"📊 Tokens: {total_input_tokens}+{total_output_tokens} | Time: {duration:.0f}ms",
                        style="dim",
                    )

            elif event.type == "message_stop":
                pass

            elif event.type == "tool_calls_done":
                pass

            elif event.type == "finish_reason":
                pass

    if answer_text:
        console.print(Markdown(answer_text))

    console.print(
        Panel(
            f"输入 Tokens: {total_input_tokens:,}\n输出 Tokens: {total_output_tokens:,}",
            title="本次查询",
            border_style="dim",
        )
    )
    if cost_tracker is not None:
        console.print(
            Panel(
                cost_tracker.session_summary.format(),
                title="累计会话费用",
                border_style="green",
            )
        )

    return answer_text


def render_todo_list(todo_list: list) -> None:
    if not todo_list:
        return
    lines = []
    for item in todo_list:
        status_icons = {
            "pending": "⏳",
            "in_progress": "🔄",
            "completed": "✅",
        }
        icon = status_icons.get(item.status, "⏳")
        priority_styles = {
            "high": "bold red",
            "medium": "yellow",
            "low": "dim",
        }
        style = priority_styles.get(item.priority, "")
        lines.append(f"  {icon} [{style}]{item.content}[/{style}]")
    console.print(Panel("\n".join(lines), title="Todo List", border_style="blue"))


AGENT_COLORS = [
    "bold cyan",
    "bold magenta",
    "bold green",
    "bold yellow",
    "bold blue",
    "bold red",
]
_agent_color_map: dict[str, str] = {}
_agent_color_index = 0


def get_agent_color(agent_name: str) -> str:
    global _agent_color_index
    if agent_name not in _agent_color_map:
        _agent_color_map[agent_name] = AGENT_COLORS[_agent_color_index % len(AGENT_COLORS)]
        _agent_color_index += 1
    return _agent_color_map[agent_name]


def render_agent_output(agent_name: str, text: str) -> None:
    color = get_agent_color(agent_name)
    console.print(f"[{color}]-agent {agent_name}:[/{color}] {text}")
