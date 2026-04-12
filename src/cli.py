from __future__ import annotations

import asyncio

import typer

from src import __version__

app = typer.Typer(
    name="clawscode",
    help="AI 编程助手 CLI - Claude Code 的 Python 复刻版",
    add_completion=False,
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def main(
    prompt: str = typer.Argument(None, help="初始提示"),
    model: str = typer.Option(None, "--model", "-m", help="模型名称"),
    version: bool = typer.Option(False, "--version", "-v", help="显示版本号"),
    print_mode: bool = typer.Option(False, "--print", help="非交互模式，输出结果后退出"),
) -> None:
    if version:
        print(f"clawscode {__version__}")
        raise typer.Exit()

    asyncio.run(_run(prompt, model, print_mode))


async def _run(prompt: str | None, model: str | None, print_mode: bool) -> None:
    from src.state import AppState
    from src.config import load_config

    settings, mcp_servers = load_config()
    if model:
        settings.model = model

    state = AppState(settings=settings)
    state.mcp_servers = mcp_servers

    if prompt is not None:
        state.messages.append({"role": "user", "content": prompt})

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
    from src.context import build_system_prompt
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

    system = build_system_prompt(state.cwd, tools)
    stream = await handle_query(
        user_input, state, system,
        permission_checker=permission_checker,
        extra_tools=extra_tools,
    )
    await render_stream(stream)
    state.messages = await compact_if_needed(state.messages, state.settings.max_tokens)
