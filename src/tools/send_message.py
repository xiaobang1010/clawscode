from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


_message_queues: dict[str, asyncio.Queue] = {}


def _get_or_create_queue(agent_id: str) -> asyncio.Queue:
    if agent_id not in _message_queues:
        _message_queues[agent_id] = asyncio.Queue()
    return _message_queues[agent_id]


def send_message_to(agent_id: str, message: str, sender: str = "") -> bool:
    queue = _get_or_create_queue(agent_id)
    try:
        queue.put_nowait({"sender": sender, "message": message})
        return True
    except asyncio.QueueFull:
        return False


def get_messages(agent_id: str) -> list[dict]:
    queue = _get_or_create_queue(agent_id)
    messages = []
    while not queue.empty():
        try:
            msg = queue.get_nowait()
            messages.append(msg)
        except asyncio.QueueEmpty:
            break
    return messages


def clear_messages(agent_id: str) -> None:
    if agent_id in _message_queues:
        while not _message_queues[agent_id].empty():
            try:
                _message_queues[agent_id].get_nowait()
            except asyncio.QueueEmpty:
                break


class SendMessageInput(BaseModel):
    target_agent: str = Field(description="目标 Agent 的 ID 或名称")
    message: str = Field(description="要发送的消息内容")


class SendMessageTool(Tool):
    name = "SendMessage"
    description = "向其他 Agent 发送消息。用于 Agent 间的协作和通信。"
    input_schema = SendMessageInput
    is_readonly = True

    async def call(self, input: SendMessageInput, context: Any) -> ToolResult:
        sender = ""
        if context and hasattr(context, "_current_agent_name"):
            sender = context._current_agent_name

        success = send_message_to(input.target_agent, input.message, sender)
        if success:
            return ToolResult(
                output=f"消息已发送到 {input.target_agent}: {input.message[:100]}"
            )
        return ToolResult(
            output=f"消息发送失败：目标 {input.target_agent} 的队列已满",
            is_error=True,
        )
