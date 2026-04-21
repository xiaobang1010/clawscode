from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class MessageSource(str, Enum):
    USER = "user"
    TEAMMATE = "teammate"
    SYSTEM = "system"
    TICK = "tick"
    TASK = "task"


class MailboxMessage:
    def __init__(
        self,
        content: str,
        sender: str = "",
        source: MessageSource = MessageSource.TEAMMATE,
        metadata: dict[str, Any] | None = None,
    ):
        self.content = content
        self.sender = sender
        self.source = source
        self.metadata = metadata or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "sender": self.sender,
            "message": self.content,
            "source": self.source.value,
            "timestamp": self.timestamp,
            **self.metadata,
        }


class Mailbox:
    def __init__(self, agent_id: str, maxsize: int = 1000):
        self._agent_id = agent_id
        self._queue: asyncio.Queue[MailboxMessage] = asyncio.Queue(maxsize=maxsize)
        self._revision = 0
        self._subscribers: list[asyncio.Event] = []

    @property
    def revision(self) -> int:
        return self._revision

    def send(self, message: MailboxMessage) -> bool:
        try:
            self._queue.put_nowait(message)
            self._revision += 1
            for event in self._subscribers:
                event.set()
            return True
        except asyncio.QueueFull:
            return False

    def poll(
        self,
        predicate: Callable[[MailboxMessage], bool] | None = None,
    ) -> list[MailboxMessage]:
        messages: list[MailboxMessage] = []
        temp: list[MailboxMessage] = []

        while not self._queue.empty():
            try:
                msg = self._queue.get_nowait()
                if predicate is None or predicate(msg):
                    messages.append(msg)
                else:
                    temp.append(msg)
            except asyncio.QueueEmpty:
                break

        for msg in temp:
            try:
                self._queue.put_nowait(msg)
            except asyncio.QueueFull:
                break

        return messages

    async def receive(
        self,
        predicate: Callable[[MailboxMessage], bool] | None = None,
        timeout: float = 30.0,
    ) -> MailboxMessage | None:
        event = asyncio.Event()
        self._subscribers.append(event)

        try:
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None

                messages = self.poll(predicate)
                if messages:
                    return messages[0]

                try:
                    await asyncio.wait_for(event.wait(), timeout=min(remaining, 1.0))
                    event.clear()
                except asyncio.TimeoutError:
                    continue
        finally:
            if event in self._subscribers:
                self._subscribers.remove(event)

    def subscribe(self) -> asyncio.Event:
        event = asyncio.Event()
        self._subscribers.append(event)
        return event


_mailboxes: dict[str, Mailbox] = {}
_message_queues: dict[str, asyncio.Queue] = {}


def _get_or_create_mailbox(agent_id: str) -> Mailbox:
    if agent_id not in _mailboxes:
        _mailboxes[agent_id] = Mailbox(agent_id)
    return _mailboxes[agent_id]


def _get_or_create_queue(agent_id: str) -> asyncio.Queue:
    if agent_id not in _message_queues:
        _message_queues[agent_id] = asyncio.Queue()
    return _message_queues[agent_id]


def send_message_to(
    agent_id: str,
    message: str,
    sender: str = "",
    source: MessageSource = MessageSource.TEAMMATE,
) -> bool:
    mb = _get_or_create_mailbox(agent_id)
    result = mb.send(MailboxMessage(content=message, sender=sender, source=source))

    queue = _get_or_create_queue(agent_id)
    try:
        queue.put_nowait({"sender": sender, "message": message, "source": source.value})
    except asyncio.QueueFull:
        pass

    return result


def get_messages(
    agent_id: str,
    predicate: Callable[[dict], bool] | None = None,
) -> list[dict]:
    mb = _get_or_create_mailbox(agent_id)
    if predicate is not None:
        def mb_predicate(msg: MailboxMessage) -> bool:
            return predicate(msg.to_dict())
        msgs = mb.poll(mb_predicate)
    else:
        msgs = mb.poll()

    queue = _get_or_create_queue(agent_id)
    legacy_messages: list[dict] = []
    while not queue.empty():
        try:
            msg = queue.get_nowait()
            legacy_messages.append(msg)
        except asyncio.QueueEmpty:
            break

    if not msgs and legacy_messages:
        if predicate is not None:
            return [m for m in legacy_messages if predicate(m)]
        return legacy_messages

    return [m.to_dict() for m in msgs] if msgs else legacy_messages


def get_mailbox(agent_id: str) -> Mailbox:
    return _get_or_create_mailbox(agent_id)


def clear_messages(agent_id: str) -> None:
    if agent_id in _mailboxes:
        _mailboxes[agent_id].poll()
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
