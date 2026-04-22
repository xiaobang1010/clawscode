from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from enum import Enum


class BackgroundTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class BackgroundTaskInfo:
    task_id: str
    agent_name: str
    status: BackgroundTaskStatus = BackgroundTaskStatus.PENDING
    output: str = ""
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    _task: asyncio.Task | None = field(default=None, repr=False)
    _on_complete_callbacks: list[Callable[[BackgroundTaskInfo], None]] = field(default_factory=list, repr=False)

    def set_task(self, task: asyncio.Task) -> None:
        self._task = task
        self.status = BackgroundTaskStatus.RUNNING
        self.started_at = time.time()

    def complete(self, output: str) -> None:
        self.output = output
        self.status = BackgroundTaskStatus.DONE
        self.completed_at = time.time()
        self._notify_complete()

    def fail(self, error: str) -> None:
        self.error = error
        self.status = BackgroundTaskStatus.ERROR
        self.completed_at = time.time()
        self._notify_complete()

    def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self.status = BackgroundTaskStatus.CANCELLED
        self.completed_at = time.time()
        self._notify_complete()

    def on_complete(self, callback: Callable[[BackgroundTaskInfo], None]) -> None:
        self._on_complete_callbacks.append(callback)
        if self.status in (BackgroundTaskStatus.DONE, BackgroundTaskStatus.ERROR, BackgroundTaskStatus.CANCELLED):
            callback(self)

    def _notify_complete(self) -> None:
        for callback in self._on_complete_callbacks:
            try:
                callback(self)
            except Exception:
                pass

    @property
    def duration_ms(self) -> int | None:
        if self.started_at is None:
            return None
        end = self.completed_at or time.time()
        return int((end - self.started_at) * 1000)

    @property
    def is_terminal(self) -> bool:
        return self.status in (BackgroundTaskStatus.DONE, BackgroundTaskStatus.ERROR, BackgroundTaskStatus.CANCELLED)


class BackgroundTaskManager:
    def __init__(self):
        self._tasks: dict[str, BackgroundTaskInfo] = {}
        self._lock = asyncio.Lock()
        self._notification_queue: asyncio.Queue[BackgroundTaskInfo] = asyncio.Queue()
        self._notification_handlers: list[Callable[[BackgroundTaskInfo], Any]] = []

    async def create_task(self, agent_name: str) -> BackgroundTaskInfo:
        import uuid
        task_id = str(uuid.uuid4())[:8]
        info = BackgroundTaskInfo(task_id=task_id, agent_name=agent_name)
        async with self._lock:
            self._tasks[task_id] = info
        return info

    async def get_task(self, task_id: str) -> BackgroundTaskInfo | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def list_tasks(self, status: BackgroundTaskStatus | None = None) -> list[BackgroundTaskInfo]:
        async with self._lock:
            tasks = list(self._tasks.values())
            if status:
                tasks = [t for t in tasks if t.status == status]
            return tasks

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            info = self._tasks.get(task_id)
            if info and not info.is_terminal:
                info.cancel()
                return True
            return False

    async def cleanup_completed(self, max_age_seconds: float = 3600) -> int:
        now = time.time()
        async with self._lock:
            to_remove = []
            for task_id, info in self._tasks.items():
                if info.is_terminal and info.completed_at:
                    if now - info.completed_at > max_age_seconds:
                        to_remove.append(task_id)
            for task_id in to_remove:
                del self._tasks[task_id]
            return len(to_remove)

    def on_notification(self, handler: Callable[[BackgroundTaskInfo], Any]) -> None:
        self._notification_handlers.append(handler)

    async def _notify(self, info: BackgroundTaskInfo) -> None:
        await self._notification_queue.put(info)
        for handler in self._notification_handlers:
            try:
                result = handler(info)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    async def notification_loop(self) -> None:
        while True:
            try:
                info = await self._notification_queue.get()
                for handler in self._notification_handlers:
                    try:
                        result = handler(info)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        pass
            except asyncio.CancelledError:
                break
            except Exception:
                pass


_task_manager: BackgroundTaskManager | None = None


def get_background_task_manager() -> BackgroundTaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager


async def create_background_task(agent_name: str) -> BackgroundTaskInfo:
    return await get_background_task_manager().create_task(agent_name)


async def get_background_task(task_id: str) -> BackgroundTaskInfo | None:
    return await get_background_task_manager().get_task(task_id)


async def list_background_tasks(status: BackgroundTaskStatus | None = None) -> list[BackgroundTaskInfo]:
    return await get_background_task_manager().list_tasks(status)


async def cancel_background_task(task_id: str) -> bool:
    return await get_background_task_manager().cancel_task(task_id)
