from __future__ import annotations

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

    if prompt is None:
        print("clawscode - AI 编程助手")
        print("输入 --help 查看帮助信息")
        raise typer.Exit()
