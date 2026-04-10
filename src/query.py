from __future__ import annotations

from typing import Any

from src.state import AppState
from src.query_engine import create_query_loop
from src.api_client import StreamEvent


async def handle_query(
    user_input: str,
    state: AppState,
    system_prompt: str,
) -> Any:
    from src.tools import get_tools

    tools = get_tools()
    user_messages = [{"role": "user", "content": user_input}]

    return create_query_loop(
        user_messages=user_messages,
        tools=tools,
        context=state,
        history=state.messages,
        system_prompt=system_prompt,
    )
