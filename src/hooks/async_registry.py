from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

from src.hooks.types import HookContext, HookDefinition, HookEvent, HookResult


class AsyncHookEntry:
    def __init__(
        self,
        name: str,
        event: HookEvent,
        callback: Callable[[HookContext], Coroutine[Any, Any, HookResult]],
        timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.event = event
        self.callback = callback
        self.timeout = timeout

    async def execute(self, context: HookContext) -> HookResult:
        try:
            result = await asyncio.wait_for(
                self.callback(context),
                timeout=self.timeout,
            )
            return result
        except asyncio.TimeoutError:
            return HookResult(error=f"Async hook '{self.name}' timed out after {self.timeout}s")
        except Exception as e:
            return HookResult(error=f"Async hook '{self.name}' failed: {e}")


class AsyncHookRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, AsyncHookEntry] = {}

    def register(
        self,
        name: str,
        event: HookEvent,
        callback: Callable[[HookContext], Coroutine[Any, Any, HookResult]],
        timeout: float = 30.0,
    ) -> None:
        self._entries[name] = AsyncHookEntry(
            name=name,
            event=event,
            callback=callback,
            timeout=timeout,
        )

    def unregister(self, name: str) -> None:
        self._entries.pop(name, None)

    async def fire(self, context: HookContext) -> list[HookResult]:
        entries = [e for e in self._entries.values() if e.event == context.event]
        if not entries:
            return []

        results = []
        for entry in entries:
            result = await entry.execute(context)
            results.append(result)
            if result.should_block:
                break

        return results

    async def fire_parallel(self, context: HookContext) -> list[HookResult]:
        entries = [e for e in self._entries.values() if e.event == context.event]
        if not entries:
            return []

        tasks = [entry.execute(context) for entry in entries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final = []
        for r in results:
            if isinstance(r, Exception):
                final.append(HookResult(error=str(r)))
            else:
                final.append(r)
                if r.should_block:
                    break

        return final

    def find_by_event(self, event: HookEvent) -> list[AsyncHookEntry]:
        return [e for e in self._entries.values() if e.event == event]

    def list_all(self) -> list[AsyncHookEntry]:
        return list(self._entries.values())

    def clear(self) -> None:
        self._entries.clear()
