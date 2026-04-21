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
from src.services.agent_context import (
    AgentContextManager,
    SubagentContext,
    create_isolated_agent_state,
)
from src.services.cache_params import (
    save_cache_safe_params,
    get_cache_safe_params,
    build_cache_safe_params,
)
from src.tool import Tool, ToolResult


class AgentToolInput(BaseModel):
    description: str = Field(description="任务的简短描述（3-5 个词）")
    prompt: str = Field(description="子 Agent 需要执行的任务描述")
    subagent_type: str | None = Field(default=None, description="Agent 类型。省略则以 fork 模式运行（继承父级上下文）")
    model: str | None = Field(default=None, description="覆盖模型")
    run_in_background: bool = Field(default=False, description="是否后台执行")
    isolation: str | None = Field(default=None, description="隔离模式: 'worktree' 在独立 git worktree 中运行")


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


def _summarize_result(text: str, max_chars: int = 3000) -> str:
    if len(text) <= max_chars:
        return text
    lines = text.split("\n")
    head_count = max(1, len(lines) // 2)
    head = "\n".join(lines[:head_count])
    tail = "\n".join(lines[-head_count:])
    return f"{head}\n\n...[摘要：共 {len(text)} 字符，已省略中间部分]...\n\n{tail}"


async def _run_agent_loop(
    messages: list[dict],
    tools: list[Tool],
    system_prompt: str,
    model: str,
    api_key: str,
    base_url: str,
    max_turns: int = 50,
    agent_name: str = "",
    agent_ctx: SubagentContext | None = None,
    agent_state: dict | None = None,
) -> str:
    ctx_mgr = AgentContextManager()
    if agent_ctx is not None:
        ctx_mgr.bind(agent_ctx, agent_state)

    collected_text = ""

    try:
        for _ in range(max_turns):
            if agent_name:
                from src.tools.send_message import get_messages
                pending = get_messages(agent_name)
                for msg in pending:
                    sender = msg.get("sender", "unknown")
                    messages.append({
                        "role": "user",
                        "content": f"[来自 {sender} 的消息] {msg.get('message', '')}",
                    })

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
    finally:
        pass

    return collected_text


class AgentTool(Tool):
    name = "Agent"
    description = (
        "启动一个新的 Agent 来自主处理复杂的多步骤任务。\n\n"
        "Agent 工具启动专门的 Agent，它们可以自主处理复杂任务。每种 Agent 类型有特定的能力和可用工具。\n\n"
        "何时使用 Agent：\n"
        "- 复杂的、需要多个步骤才能完成的任务\n"
        "- 需要自主决策的研究和探索工作\n"
        "- 需要独立执行的实现工作\n"
        "- 需要多个工具协调使用的场景\n\n"
        "何时不使用 Agent：\n"
        "- 如果你想读取特定文件，直接使用 FileRead 或 Glob 工具，更快\n"
        "- 如果你搜索特定类定义如 'class Foo'，直接使用 Grep 工具\n"
        "- 如果只需在 2-3 个文件中搜索代码，使用 FileRead 工具\n"
        "- 其他与 Agent 能力无关的任务\n\n"
        "使用说明：\n"
        "- 始终包含一个简短描述（3-5 个词），概括 Agent 将要做什么\n"
        "- 尽可能并行启动多个 Agent 以最大化性能；使用单条消息中的多个工具调用来实现\n"
        "- 当 Agent 完成时，它会返回一条消息。返回的结果对用户不可见。要向用户展示结果，你应该发送一条包含结果摘要的文本消息\n"
        "- 可以选择使用 run_in_background 参数在后台运行 Agent。Agent 在后台运行时，完成后会自动通知——不要 sleep、轮询或主动检查进度\n"
        "- 前台 vs 后台：当需要 Agent 的结果才能继续时使用前台（默认）；当你有真正独立的工作可以并行完成时使用后台\n\n"
        "编写 Agent prompt 的指导：\n"
        "像给刚走进房间的聪明同事做简报一样——它没看到过这个对话，不知道你尝试了什么，不理解这个任务为什么重要。\n"
        "- 解释你想完成什么以及为什么\n"
        "- 描述你已经了解或排除的内容\n"
        "- 提供足够的上下文让 Agent 能做出判断，而不仅仅是遵循狭窄的指令\n"
        "- 如果需要简短回复，明确说明（'200 字以内报告'）\n"
        "- 不要委托理解：不要写'根据你的发现修复 bug'，要写具体的文件路径、行号、要更改什么\n\n"
        "**不要偷看。** Agent 运行期间不要主动读取或检查其输出。你会收到完成通知；信任它。\n"
        "**不要抢跑。** 启动后，你对 Agent 发现了什么一无所知。永远不要捏造或预测 Agent 结果。"
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
        is_fork = input.subagent_type is None
        if is_fork:
            definition = _find_agent_definition("general-purpose")
        else:
            definition = _find_agent_definition(input.subagent_type)
        if not definition:
            return ToolResult(
                output=f"未找到 Agent 类型: {input.subagent_type}",
                is_error=True,
            )

        from src.tools import get_tools
        all_tools = get_tools()
        builder = AgentBuilder(all_tools)

        if is_fork:
            agent_tools = all_tools
        else:
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

        if is_fork:
            cached_params = get_cache_safe_params()
            if cached_params and cached_params.system_prompt:
                system_prompt = cached_params.system_prompt
            elif context:
                from src.services.prompt_builder import PromptBuilder
                parent_sp = getattr(context, "_current_system_prompt", "")
                system_prompt = parent_sp
            else:
                system_prompt = builder.build_system_prompt(definition)
            if not system_prompt:
                system_prompt = builder.build_system_prompt(definition)
        else:
            system_prompt = builder.build_system_prompt(definition)

        if is_fork:
            agent_messages: list[dict] = []
            if context:
                parent_messages = getattr(context, "messages", [])
                if parent_messages:
                    agent_messages = list(parent_messages)
            agent_messages.append({"role": "user", "content": input.prompt})
        else:
            agent_messages = [{"role": "user", "content": input.prompt}]

        if definition.memory:
            memory = AgentMemory(
                cwd=getattr(context, "cwd", __import__("pathlib").Path.cwd()),
                agent_name=definition.name,
            )
            memory.load_from_memory_files()
            mem_text = memory.format_for_prompt()
            if mem_text:
                system_prompt += f"\n\n{mem_text}"

        agent_id = _display_manager.register_agent(
            definition.name if not is_fork else "fork"
        )

        worktree_isolation = None
        effective_cwd = getattr(context, "cwd", None) if context else None
        if input.isolation == "worktree" and effective_cwd:
            from src.utils.worktree import WorktreeIsolation
            from src.utils.git import is_git_repo
            if is_git_repo(effective_cwd):
                worktree_isolation = WorktreeIsolation(effective_cwd, definition.name)
                worktree_isolation.__enter__()
                if worktree_isolation.worktree_dir:
                    for m in agent_messages:
                        if m.get("role") == "user" and isinstance(m.get("content"), str):
                            m["content"] += f"\n[Worktree 隔离] 工作目录: {worktree_isolation.worktree_dir}"

        agent_ctx = SubagentContext(
            agent_id=str(agent_id),
            parent_session_id=getattr(context, "session_id", ""),
            subagent_name=definition.name,
            is_built_in=True,
        )
        isolated_state = create_isolated_agent_state(
            parent_state={"read_files": getattr(context, "read_files", set())} if context else None,
            share_read_files=True,
        )

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
                        agent_name=definition.name,
                        agent_ctx=agent_ctx,
                        agent_state=isolated_state,
                    )
                    summary = _summarize_result(result_text)
                    bg_task.complete(summary)
                except Exception as e:
                    bg_task.fail(str(e))
                finally:
                    await self._fire_subagent_hook(context, HookEvent.SUBAGENT_STOP, definition.name, agent_id)
                    _display_manager.deactivate(agent_id)

            import asyncio as _aio
            task = _aio.create_task(_bg_run())
            bg_task.set_task(task)

            return ToolResult(
                output=f"后台 Agent 已启动 (ID: {task_id}, 模式: {'fork' if is_fork else 'fresh'}, 类型: {definition.name})"
            )

        await self._fire_subagent_hook(context, HookEvent.SUBAGENT_START, definition.name, agent_id)
        _display_manager.activate(agent_id)
        try:
            result_text = await _run_agent_loop(
                agent_messages, agent_tools, system_prompt,
                model, api_key, base_url, definition.max_turns,
                agent_name=definition.name,
                agent_ctx=agent_ctx,
                agent_state=isolated_state,
            )
            summary = _summarize_result(result_text)

            save_cache_safe_params(build_cache_safe_params(
                system_prompt=system_prompt,
                tools=[t.get_openai_tool_schema() for t in agent_tools],
                messages=agent_messages,
                model=model,
                base_url=base_url,
                api_key=api_key,
            ))

            return ToolResult(output=summary)
        except Exception as e:
            return ToolResult(output=f"Agent 执行错误: {e}", is_error=True)
        finally:
            await self._fire_subagent_hook(context, HookEvent.SUBAGENT_STOP, definition.name, agent_id)
            _display_manager.deactivate(agent_id)
            if worktree_isolation is not None:
                worktree_isolation.__exit__(None, None, None)


def get_background_tasks() -> dict[str, _BackgroundTask]:
    return dict(_background_tasks)


def get_background_task(task_id: str) -> _BackgroundTask | None:
    return _background_tasks.get(task_id)


def get_display_manager() -> AgentDisplayManager:
    return _display_manager
