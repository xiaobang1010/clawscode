from __future__ import annotations

import asyncio

import typer

from src import __version__

app = typer.Typer(
    name="clawscode",
    help="AI 编程助手 CLI ",
    add_completion=False,
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def main(
    prompt: str = typer.Argument(None, help="初始提示"),
    model: str = typer.Option(None, "--model", "-m", help="模型名称"),
    version: bool = typer.Option(False, "--version", "-v", help="显示版本号"),
    print_mode: bool = typer.Option(False, "--print", help="非交互模式，输出结果后退出"),
    resume: str = typer.Option(None, "--resume", "-r", help="恢复历史会话（会话 ID 或 'latest'）"),
) -> None:
    if version:
        print(f"clawscode {__version__}")
        raise typer.Exit()

    asyncio.run(_run(prompt, model, print_mode, resume))


async def _run(prompt: str | None, model: str | None, print_mode: bool, resume: str | None) -> None:
    from src.state import AppState
    from src.config import load_config
    from src.services.session_restore import SessionRestore
    from src.services.session_storage import SessionStorage
    from src.services.session_title import generate_title
    from src.repl import console

    settings, mcp_servers = load_config()
    if model:
        settings.model = model

    state = AppState(settings=settings)
    state.mcp_servers = mcp_servers

    from src.services.cost_tracker import CostTrackerService
    state.cost_tracker_service = CostTrackerService(
        model=settings.model,
        custom_pricing=settings.cost.pricing or None,
    )

    if resume is not None:
        storage_path = settings.session.storage_path if hasattr(settings, "session") else ""
        restorer = SessionRestore(storage=SessionStorage(storage_path=storage_path))
        session_id = None if resume == "latest" else resume
        if session_id is None:
            restored = restorer.restore_latest()
        else:
            restored = restorer.restore(session_id)

        if restored is not None:
            state.messages = restored.messages
            state.session_id = restored.session_data.session_id
            state.session_title = restored.session_data.title
            console.print(f"已恢复会话: {state.session_title or state.session_id[:8]}", style="bold green")
            console.print(f"  消息数: {len(state.messages)}", style="dim")
        else:
            if session_id:
                console.print(f"未找到会话: {session_id}", style="bold red")
            else:
                console.print("没有可恢复的历史会话", style="bold yellow")

    if prompt is not None:
        state.messages.append({"role": "user", "content": prompt})
        if not state.session_title:
            state.session_title = generate_title(prompt)

    if print_mode:
        if prompt is None:
            print("错误：--print 模式需要提供 prompt 参数")
            raise typer.Exit(1)
        await _run_query(state, prompt)
        return

    await _run_repl(state, initial_prompt=prompt)


async def _run_repl(state: AppState, initial_prompt: str | None = None) -> None:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory

    from src.commands import CommandRegistry, register_commands
    from src.repl import console

    history_dir = state.cwd / ".clawscode"
    history_dir.mkdir(exist_ok=True)
    session = PromptSession(history=FileHistory(str(history_dir / "history")))
    registry = CommandRegistry()
    register_commands(registry)

    mcp_client = await _init_mcp(state)

    if initial_prompt is None:
        console.print("clawscode - AI 编程助手", style="bold green")
        console.print("输入 /help 查看可用命令\n")

    if initial_prompt is not None:
        await _run_query(state, initial_prompt)

    try:
        while True:
            try:
                user_input = await session.prompt_async("clawscode> ")
            except KeyboardInterrupt:
                continue
            except EOFError:
                break

            if not user_input.strip():
                continue

            if registry.is_command(user_input):
                result = await registry.execute(user_input, state)
                if result:
                    console.print(result)
                continue

            await _run_query(state, user_input)
    finally:
        try:
            from src.hooks.types import HookContext, HookEvent
            from src.hooks.executor import HookExecutor
            from src.hooks.config import load_hooks_into_registry
            from src.hooks.registry import HookRegistry
            settings_dict = None
            if hasattr(state, 'settings') and hasattr(state.settings, 'hooks'):
                hooks_cfg = state.settings.hooks
                if hooks_cfg.enabled:
                    settings_dict = {"hooks": hooks_cfg.hooks}
            if settings_dict is not None:
                reg = HookRegistry()
                count = load_hooks_into_registry(reg, settings=settings_dict)
                if count > 0:
                    executor = HookExecutor(reg)
                    ctx = HookContext(event=HookEvent.SESSION_END, session_id=state.session_id)
                    await executor.execute(ctx)
        except Exception:
            pass
        if mcp_client is not None:
            await mcp_client.disconnect_all()


async def _init_mcp(state: AppState) -> Any:
    from src.services.mcp_client import MCPClient
    from src.tools.mcp_tool import MCPToolAdapter

    if not state.mcp_servers:
        state._mcp_client = None
        state._extra_tools = []
        return None

    client = MCPClient(state.mcp_servers)
    await client.connect_all()
    state._mcp_client = client

    status = client.get_status()
    connected = sum(1 for s in status.values() if s == "connected")
    console.print(f"MCP: {connected}/{len(status)} 个服务器已连接", style="dim")

    mcp_tools: list[MCPToolAdapter] = []
    if client.sessions:
        tools_list = await client.list_tools()
        for t in tools_list:
            adapter = MCPToolAdapter(
                name=t["name"],
                description=t["description"],
                input_schema_dict=t["schema"],
                client=client,
            )
            mcp_tools.append(adapter)
        if mcp_tools:
            console.print(f"MCP: 已加载 {len(mcp_tools)} 个工具", style="dim")

    state._extra_tools = mcp_tools
    return client


async def _run_query(state: AppState, user_input: str) -> None:
    from src.context import build_context
    from src.query import handle_query
    from src.repl import render_stream
    from src.compact import compact_if_needed
    from src.permissions import PermissionChecker

    tools = []
    try:
        from src.tools import get_tools
        tools = get_tools()
    except Exception:
        pass

    extra_tools = getattr(state, "_extra_tools", None)
    permission_checker = PermissionChecker(state.settings)
    state.permission_checker = permission_checker

    system = build_context(state.cwd, tools, memory_config=state.settings.memory)
    stream = await handle_query(
        user_input, state, system,
        permission_checker=permission_checker,
        extra_tools=extra_tools,
    )
    await render_stream(stream)
    state.messages = await compact_if_needed(state.messages, state.settings.max_tokens)
