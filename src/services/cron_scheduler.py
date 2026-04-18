from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class CronTask:
    id: str
    name: str
    command: str
    interval_seconds: float
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    error_count: int = 0
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "command": self.command,
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "metadata": self.metadata,
        }


class CronScheduler:
    def __init__(self) -> None:
        self._tasks: dict[str, CronTask] = {}
        self._running: bool = False
        self._background_task: asyncio.Task | None = None
        self._executor: Callable[[str], Awaitable[str]] | None = None
        self._lock = asyncio.Lock()

    def set_executor(self, executor: Callable[[str], Awaitable[str]]) -> None:
        self._executor = executor

    def create_task(
        self,
        name: str,
        command: str,
        interval_seconds: float,
        metadata: dict[str, Any] | None = None,
    ) -> CronTask:
        task_id = uuid.uuid4().hex[:8]
        task = CronTask(
            id=task_id,
            name=name,
            command=command,
            interval_seconds=max(1.0, interval_seconds),
            metadata=metadata or {},
        )
        self._tasks[task_id] = task
        logger.info("Created cron task '%s' (id=%s, interval=%ss)", name, task_id, interval_seconds)
        return task

    def delete_task(self, task_id: str) -> CronTask | None:
        task = self._tasks.pop(task_id, None)
        if task:
            logger.info("Deleted cron task '%s' (id=%s)", task.name, task_id)
        return task

    def get_task(self, task_id: str) -> CronTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[CronTask]:
        return list(self._tasks.values())

    def enable_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task:
            task.enabled = True
            return True
        return False

    def disable_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task:
            task.enabled = False
            return True
        return False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._background_task = asyncio.create_task(self._run_loop())
        logger.info("Cron scheduler started")

    async def stop(self) -> None:
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
        logger.info("Cron scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _run_loop(self) -> None:
        while self._running:
            now = datetime.now()
            for task in list(self._tasks.values()):
                if not task.enabled:
                    continue

                if task.next_run is None or now >= task.next_run:
                    asyncio.create_task(self._execute_task(task))

            await asyncio.sleep(1.0)

    async def _execute_task(self, task: CronTask) -> None:
        from datetime import timedelta

        async with self._lock:
            if self._executor is None:
                task.last_error = "No executor configured"
                task.error_count += 1
                task.next_run = datetime.now() + timedelta(seconds=task.interval_seconds)
                return

        try:
            logger.debug("Executing cron task '%s'", task.name)
            result = await self._executor(task.command)
            task.last_run = datetime.now()
            task.run_count += 1
            task.last_error = None
            logger.debug("Cron task '%s' completed: %s", task.name, result[:100])
        except Exception as e:
            task.error_count += 1
            task.last_error = str(e)
            logger.warning("Cron task '%s' failed: %s", task.name, e)
        finally:
            task.next_run = datetime.now() + timedelta(seconds=task.interval_seconds)


_scheduler: CronScheduler | None = None


def get_cron_scheduler() -> CronScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler
