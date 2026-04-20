from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from src.agents.agent_definition import AgentDefinition
from src.agents.builder import AgentBuilder
from src.agents.display import AgentDisplayManager
from src.agents.memory import AgentMemory, MemoryScope
from src.agents.builtins import get_builtin_agents
from src.api_client import StreamEvent, create_stream
from src.tool import Tool, ToolResult


class AgentToolInput(BaseModel):
    description: str = Field(description="任务的简短描述（3-5 个词）")
    prompt: str = Field(description="子 Agent 需要执行的任务描述")
    subagent_type: str = Field(default="general-purpose", description="Agent 类型")
    model: str | None = Field(default=None, description="覆盖模型")
    run_in_background: bool = Field(default=False, description="是否后台执行")


_background_tasks: dict[str, _BackgroundTask] = {}
_display_manager = AgentDisplayManager()


class _BackgroundTask:
    def __init__(self, task_id: str, agent_name: str):
        self.task_id = task_id
        self.agent_name = agent_name
        self.output: str = ""
        self.status: str = "running"
        self.created_at: float = time.time()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def set_task(self, task: asyncio.Task) -> None:
        self._task = task

    def append_output(self, text: str) -> None:
        self.output += text

    def complete(self, final_output: str) -> None:
        self.output = final_output
        self.status = "done"

    def fail(self, error: str) -> None:
        self.output = error
        self.status = "error"

    def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self.status = "cancelled"


def _find_agent_definition(subagent_type: str) -> AgentDefinition | None:
    for agent in get_builtin_agents():
        if agent.name == subagent_type:
            return agent
    return None


async def _run_agent_loop(
    messages: list[dict],
    tools: list[Tool],
    system_prompt: str,
    model: str,
    api_key: str,
    base_url: str,
    max_turns: int = 50,
) -> str:
    collected_text = ""

    for _ in range(max_turns):
        tool_schemas = [t.get_openai_tool_schema() for t in tools]
        tool_map = {t.name: t for t in tools}

        has_tool_calls = False
        current_tool_calls: dict[int, dict] = {}
        text_parts: list[str] = []

        async for event in create_stream(
            messages,
            tool_schemas,
            system_prompt,
            model=model,
            api_key=api_key,
            base_url=base_url,
        ):
            if event.type == "text_delta":
                text_parts.append(event.data.get("text", ""))
            elif event.type == "tool_calls":
                has_tool_calls = True
                idx = event.data.get("index", 0)
                if idx not in current_tool_calls:
                    current_tool_calls[idx] = {
                        "id": event.data["id"],
                        "name": event.data["name"],
                        "arguments": "",
                    }
                current_tool_calls[idx]["arguments"] += event.data.get("arguments") or ""

        collected_text += "".join(text_parts)

        if not has_tool_calls:
            break

        assistant_content = []
        for idx in sorted(current_tool_calls):
            tc = current_tool_calls[idx]
            assistant_content.append(
                {
                    "type": "function",
                    "id": tc["id"],
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
            )

        sorted_tcs = [current_tool_calls[idx] for idx in sorted(current_tool_calls)]

        async def _exec(tc: dict) -> tuple[dict, ToolResult]:
            tool = tool_map.get(tc["name"])
            if not tool:
                return tc, ToolResult(output=f"未知工具: {tc['name']}", is_error=True)
            try:
                tool_input = tool.input_schema(**json.loads(tc["arguments"]))
                result = await tool.call(tool_input, None)
            except Exception as e:
                result = ToolResult(output=f"工具执行错误: {e}", is_error=True)
            max_chars = getattr(tool, "max_result_size_chars", 25000)
            if len(result.output) > max_chars:
                result = result.truncate(max_chars)
            return tc, result

        results = await asyncio.gather(*[_exec(tc) for tc in sorted_tcs])

        messages.append(
            {"role": "assistant", "content": None, "tool_calls": assistant_content}
        )
        for tc, result in results:
            messages.append(
                {"role": "tool", "tool_call_id": tc["id"], "content": result.output}
            )

    return collected_text


class AgentTool(Tool):
    name = "Agent"
    description = (
        "启动子 Agent 并分配任务。子 Agent 继承父级上下文，可以同步、后台或并行执行。"
    )
    input_schema = AgentToolInput
    is_readonly = False

    @staticmethod
    async def _fire_subagent_hook(context: Any, event: Any, agent_name: str, agent_id: int) -> None:
        try:
            from src.hooks.types import HookContext, HookEvent
            from src.hooks.executor import HookExecutor
            from src.hooks.config import load_hooks_into_registry
            from src.hooks.registry import HookRegistry
            settings_dict = None
            if context and hasattr(context, 'settings') and hasattr(context.settings, 'hooks'):
                hooks_cfg = context.settings.hooks
                if hooks_cfg.enabled:
                    settings_dict = {"hooks": hooks_cfg.hooks}
            if settings_dict is not None:
                reg = HookRegistry()
                count = load_hooks_into_registry(reg, settings=settings_dict)
                if count > 0:
                    executor = HookExecutor(reg)
                    ctx = HookContext(
                        event=event,
                        metadata={"agent_name": agent_name, "agent_id": agent_id},
                        session_id=getattr(context, "session_id", ""),
                    )
                    await executor.execute(ctx)
        except Exception:
            pass

    async def call(self, input: AgentToolInput, context: Any) -> ToolResult:
        definition = _find_agent_definition(input.subagent_type)
        if not definition:
            return ToolResult(
                output=f"未找到 Agent 类型: {input.subagent_type}",
                is_error=True,
            )

        from src.tools import get_tools
        all_tools = get_tools()
        builder = AgentBuilder(all_tools)
        agent_tools = builder.build_tools(definition)

        model = input.model or definition.get_model_override()
        if not model and context:
            model = getattr(context.settings, "model", "ZhipuAI/GLM-5")
        if not model:
            model = "ZhipuAI/GLM-5"

        api_key = ""
        base_url = "https://api-inference.modelscope.cn/v1"
        if context:
            api_key = getattr(context.settings, "api_key", "")
            base_url = getattr(context.settings, "base_url", base_url)

        system_prompt = builder.build_system_prompt(definition)

        agent_messages: list[dict] = []
        if context and not definition.isolation:
            parent_messages = getattr(context, "messages", [])
            if parent_messages:
                agent_messages = list(parent_messages)

        agent_messages.append({"role": "user", "content": input.prompt})

        if definition.memory:
            memory = AgentMemory(
                cwd=getattr(context, "cwd", __import__("pathlib").Path.cwd()),
                agent_name=definition.name,
            )
            memory.load_from_memory_files()
            mem_text = memory.format_for_prompt()
            if mem_text:
                system_prompt += f"\n\n{mem_text}"

        agent_id = _display_manager.register_agent(definition.name)

        if input.run_in_background:
            task_id = str(uuid.uuid4())[:8]
            bg_task = _BackgroundTask(task_id, definition.name)
            _background_tasks[task_id] = bg_task

            async def _bg_run() -> None:
                try:
                    await self._fire_subagent_hook(context, HookEvent.SUBAGENT_START, definition.name, agent_id)
                    _display_manager.activate(agent_id)
                    result_text = await _run_agent_loop(
                        agent_messages, agent_tools, system_prompt,
                        model, api_key, base_url, definition.max_turns,
                    )
                    bg_task.complete(result_text)
                except Exception as e:
                    bg_task.fail(str(e))
                finally:
                    await self._fire_subagent_hook(context, HookEvent.SUBAGENT_STOP, definition.name, agent_id)
                    _display_manager.deactivate(agent_id)

            import asyncio as _aio
            task = _aio.create_task(_bg_run())
            bg_task.set_task(task)

            return ToolResult(
                output=f"后台 Agent 已启动 (ID: {task_id}, 类型: {definition.name})"
            )

        await self._fire_subagent_hook(context, HookEvent.SUBAGENT_START, definition.name, agent_id)
        _display_manager.activate(agent_id)
        try:
            result_text = await _run_agent_loop(
                agent_messages, agent_tools, system_prompt,
                model, api_key, base_url, definition.max_turns,
            )
            return ToolResult(output=result_text)
        except Exception as e:
            return ToolResult(output=f"Agent 执行错误: {e}", is_error=True)
        finally:
            await self._fire_subagent_hook(context, HookEvent.SUBAGENT_STOP, definition.name, agent_id)
            _display_manager.deactivate(agent_id)


def get_background_tasks() -> dict[str, _BackgroundTask]:
    return dict(_background_tasks)


def get_background_task(task_id: str) -> _BackgroundTask | None:
    return _background_tasks.get(task_id)


def get_display_manager() -> AgentDisplayManager:
    return _display_manager
