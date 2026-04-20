from __future__ import annotations

from typing import Any

from src.hooks.executor import HookExecutor
from src.hooks.config import load_hooks_into_registry
from src.hooks.registry import HookRegistry
from src.hooks.types import HookContext, HookEvent
from src.permissions import PermissionChecker
from src.state import AppState
from src.tool import Tool
from src.query_engine import create_query_loop
from src.api_client import StreamEvent


def _build_hook_executor(state: AppState) -> HookExecutor | None:
    settings_dict: dict[str, Any] | None = None
    if hasattr(state, 'settings') and hasattr(state.settings, 'hooks'):
        hooks_cfg = state.settings.hooks
        if not hooks_cfg.enabled:
            return None
        settings_dict = {"hooks": hooks_cfg.hooks}
    try:
        registry = HookRegistry()
        count = load_hooks_into_registry(registry, settings=settings_dict)
        if count > 0:
            return HookExecutor(registry)
    except Exception:
        pass
    return None


async def handle_query(
    user_input: str,
    state: AppState,
    system_prompt: str,
    permission_checker: PermissionChecker | None = None,
    extra_tools: list[Tool] | None = None,
    hook_executor: HookExecutor | None = None,
) -> Any:
    from src.tools import get_tools

    tools = get_tools()
    if extra_tools is not None:
        tools = tools + extra_tools

    user_messages = [{"role": "user", "content": user_input}]
    executor = hook_executor or _build_hook_executor(state)
    if executor is not None:
        prompt_ctx = HookContext(
            event=HookEvent.USER_PROMPT_SUBMIT,
            metadata={"prompt": user_input},
            session_id=state.session_id,
        )
        await executor.execute(prompt_ctx)

    return create_query_loop(
        user_messages=user_messages,
        tools=tools,
        context=state,
        history=state.messages,
        system_prompt=system_prompt,
        permission_checker=permission_checker,
        hook_executor=executor,
    )
