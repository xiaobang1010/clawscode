from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any


@dataclass
class Argument:
    name: str
    is_dangerous: bool = False
    is_variadic: bool = False
    is_optional: bool = False
    is_command: bool = False
    is_module: bool = False
    is_script: bool = False


@dataclass
class Option:
    name: str
    short_name: str = ""
    is_dangerous: bool = False
    takes_value: bool = False
    description: str = ""


@dataclass
class CommandSpec:
    name: str
    description: str = ""
    subcommands: dict[str, CommandSpec] = field(default_factory=dict)
    args: list[Argument] = field(default_factory=list)
    options: list[Option] = field(default_factory=list)
    is_dangerous: bool = False

    def get_argument(self, index: int) -> Argument | None:
        for i, arg in enumerate(self.args):
            if i == index:
                return arg
            if arg.is_variadic and index >= i:
                return arg
        return None

    def get_option(self, name: str) -> Option | None:
        for opt in self.options:
            if opt.name == name or opt.short_name == name:
                return opt
        return None


_BUILTIN_SPECS: dict[str, CommandSpec] = {}


def _register(spec: CommandSpec) -> None:
    _BUILTIN_SPECS[spec.name] = spec


def _init_specs() -> None:
    if _BUILTIN_SPECS:
        return

    _register(CommandSpec(
        name="git",
        description="Git 版本控制系统",
        subcommands={
            "commit": CommandSpec(
                name="commit",
                description="提交变更",
                options=[
                    Option(name="--author", short_name="", is_dangerous=True, takes_value=True, description="篡改作者"),
                    Option(name="--date", short_name="", is_dangerous=True, takes_value=True, description="篡改日期"),
                    Option(name="--exec", short_name="-e", is_dangerous=True, takes_value=True, description="执行命令"),
                    Option(name="--message", short_name="-m", takes_value=True),
                    Option(name="--amend", is_dangerous=True),
                    Option(name="--all", short_name="-a"),
                ],
            ),
            "push": CommandSpec(
                name="push",
                description="推送变更",
                options=[
                    Option(name="--force", short_name="-f", is_dangerous=True),
                    Option(name="--force-with-lease"),
                ],
                is_dangerous=True,
            ),
            "reset": CommandSpec(
                name="reset",
                description="重置 HEAD",
                options=[
                    Option(name="--hard", is_dangerous=True),
                    Option(name="--soft"),
                ],
                is_dangerous=True,
            ),
            "clean": CommandSpec(
                name="clean",
                description="清理未跟踪文件",
                options=[
                    Option(name="--force", short_name="-f", is_dangerous=True),
                    Option(name="-d", is_dangerous=True),
                    Option(name="-x", is_dangerous=True),
                ],
                is_dangerous=True,
            ),
            "checkout": CommandSpec(
                name="checkout",
                description="切换分支/恢复文件",
                options=[
                    Option(name="--force", short_name="-f", is_dangerous=True),
                ],
            ),
            "rebase": CommandSpec(
                name="rebase",
                description="变基",
                options=[
                    Option(name="--interactive", short_name="-i"),
                    Option(name="--force-rebase"),
                ],
            ),
        },
    ))

    _register(CommandSpec(
        name="npm",
        description="Node.js 包管理器",
        subcommands={
            "install": CommandSpec(name="install", description="安装包"),
            "uninstall": CommandSpec(name="uninstall", description="卸载包", is_dangerous=True),
            "run": CommandSpec(name="run", description="运行脚本", args=[Argument(name="script", is_command=True)]),
            "exec": CommandSpec(name="exec", description="执行命令", args=[Argument(name="command", is_command=True, is_dangerous=True)]),
        },
    ))

    _register(CommandSpec(
        name="pip",
        description="Python 包管理器",
        subcommands={
            "install": CommandSpec(name="install", description="安装包"),
            "uninstall": CommandSpec(name="uninstall", description="卸载包", is_dangerous=True),
        },
    ))

    _register(CommandSpec(
        name="python",
        description="Python 解释器",
        args=[Argument(name="script", is_script=True)],
        options=[
            Option(name="--command", short_name="-c", takes_value=True, description="执行命令"),
            Option(name="--module", short_name="-m", takes_value=True, description="运行模块"),
        ],
    ))

    _register(CommandSpec(
        name="node",
        description="Node.js 运行时",
        args=[Argument(name="script", is_script=True)],
        options=[
            Option(name="--eval", short_name="-e", takes_value=True, description="执行代码"),
            Option(name="--require", short_name="-r", takes_value=True),
        ],
    ))

    _register(CommandSpec(
        name="docker",
        description="Docker 容器管理",
        subcommands={
            "run": CommandSpec(
                name="run",
                description="运行容器",
                args=[Argument(name="image"), Argument(name="command", is_command=True, is_dangerous=True)],
                options=[
                    Option(name="--volume", short_name="-v", takes_value=True),
                    Option(name="--privileged", is_dangerous=True),
                    Option(name="--network", takes_value=True),
                ],
            ),
            "exec": CommandSpec(
                name="exec",
                description="在容器中执行命令",
                args=[Argument(name="container"), Argument(name="command", is_command=True, is_dangerous=True)],
            ),
            "rm": CommandSpec(name="rm", description="删除容器", is_dangerous=True),
            "rmi": CommandSpec(name="rmi", description="删除镜像", is_dangerous=True),
        },
    ))

    _register(CommandSpec(
        name="kubectl",
        description="Kubernetes CLI",
        subcommands={
            "delete": CommandSpec(name="delete", description="删除资源", is_dangerous=True),
            "exec": CommandSpec(
                name="exec",
                description="在 Pod 中执行命令",
                args=[Argument(name="pod"), Argument(name="command", is_command=True, is_dangerous=True)],
            ),
            "apply": CommandSpec(name="apply", description="应用配置"),
        },
    ))

    _register(CommandSpec(
        name="rm",
        description="删除文件",
        options=[
            Option(name="--recursive", short_name="-r", is_dangerous=True),
            Option(name="--force", short_name="-f", is_dangerous=True),
        ],
        is_dangerous=True,
    ))

    _register(CommandSpec(
        name="chmod",
        description="修改文件权限",
        options=[
            Option(name="--recursive", short_name="-R", is_dangerous=True),
        ],
    ))

    _register(CommandSpec(
        name="chown",
        description="修改文件所有者",
        options=[
            Option(name="--recursive", short_name="-R", is_dangerous=True),
        ],
    ))

    _register(CommandSpec(
        name="dd",
        description="磁盘复制",
        is_dangerous=True,
        options=[
            Option(name="if=", takes_value=True, is_dangerous=True),
            Option(name="of=", takes_value=True, is_dangerous=True),
        ],
    ))

    _register(CommandSpec(name="mkfs", description="格式化文件系统", is_dangerous=True))
    _register(CommandSpec(name="shutdown", description="关机", is_dangerous=True))
    _register(CommandSpec(name="reboot", description="重启", is_dangerous=True))
    _register(CommandSpec(name="halt", description="停机", is_dangerous=True))
    _register(CommandSpec(name="poweroff", description="断电", is_dangerous=True))

    _register(CommandSpec(
        name="systemctl",
        description="系统服务管理",
        subcommands={
            "stop": CommandSpec(name="stop", description="停止服务", is_dangerous=True),
            "disable": CommandSpec(name="disable", description="禁用服务", is_dangerous=True),
            "mask": CommandSpec(name="mask", description="屏蔽服务", is_dangerous=True),
            "start": CommandSpec(name="start", description="启动服务"),
            "status": CommandSpec(name="status", description="查看状态"),
        },
    ))

    _register(CommandSpec(
        name="curl",
        description="HTTP 请求工具",
        options=[
            Option(name="--output", short_name="-o", takes_value=True),
            Option(name="--data", short_name="-d", takes_value=True),
        ],
    ))

    _register(CommandSpec(
        name="wget",
        description="下载工具",
        options=[
            Option(name="--output-document", short_name="-O", takes_value=True),
        ],
    ))

    _register(CommandSpec(
        name="jq",
        description="JSON 处理工具",
        args=[Argument(name="filter", is_dangerous=True)],
        options=[
            Option(name="--from-file", short_name="-f", takes_value=True, is_dangerous=True),
            Option(name="-L", takes_value=True),
        ],
    ))

    _register(CommandSpec(
        name="find",
        description="查找文件",
        options=[
            Option(name="--exec", short_name="-exec", takes_value=True, is_dangerous=True),
            Option(name="--delete", is_dangerous=True),
        ],
    ))

    _register(CommandSpec(name="ls", description="列出文件"))
    _register(CommandSpec(name="cat", description="查看文件"))
    _register(CommandSpec(name="head", description="查看文件头"))
    _register(CommandSpec(name="tail", description="查看文件尾"))
    _register(CommandSpec(name="grep", description="搜索文本"))
    _register(CommandSpec(name="sort", description="排序"))
    _register(CommandSpec(name="wc", description="统计"))
    _register(CommandSpec(name="echo", description="输出文本"))
    _register(CommandSpec(name="tree", description="目录树"))
    _register(CommandSpec(name="ps", description="进程列表"))
    _register(CommandSpec(name="env", description="环境变量"))
    _register(CommandSpec(name="whoami", description="当前用户"))
    _register(CommandSpec(name="date", description="日期"))
    _register(CommandSpec(name="uname", description="系统信息"))
    _register(CommandSpec(name="which", description="查找命令"))
    _register(CommandSpec(name="file", description="文件类型"))
    _register(CommandSpec(name="stat", description="文件状态"))
    _register(CommandSpec(name="diff", description="比较文件"))
    _register(CommandSpec(name="mv", description="移动文件", is_dangerous=True))
    _register(CommandSpec(name="cp", description="复制文件"))


@lru_cache(maxsize=256)
def get_command_spec(command: str) -> CommandSpec | None:
    _init_specs()

    parts = command.strip().split()
    if not parts:
        return None

    base = parts[0].split("/")[-1]
    spec = _BUILTIN_SPECS.get(base)
    if spec is None:
        return None

    if len(parts) > 1 and spec.subcommands:
        subcmd = parts[1].lstrip("-")
        sub_spec = spec.subcommands.get(subcmd)
        if sub_spec:
            return sub_spec

    return spec


def analyze_command_args(command: str) -> list[dict[str, Any]]:
    parts = command.strip().split()
    if len(parts) < 2:
        return []

    base = parts[0].split("/")[-1]
    spec = _BUILTIN_SPECS.get(base)
    if spec is None:
        return []

    subcmd = None
    arg_start = 1

    if len(parts) > 1 and spec.subcommands:
        candidate = parts[1].lstrip("-")
        if candidate in spec.subcommands:
            subcmd = candidate
            spec = spec.subcommands[candidate]
            arg_start = 2

    warnings: list[dict[str, Any]] = []

    if spec.is_dangerous:
        warnings.append({
            "type": "dangerous_command",
            "message": f"命令 '{spec.name}' 被标记为危险操作",
            "severity": "high",
        })

    for i in range(arg_start, len(parts)):
        part = parts[i]
        if part.startswith("-"):
            opt_name = part.split("=")[0]
            opt = spec.get_option(opt_name)
            if opt and opt.is_dangerous:
                warnings.append({
                    "type": "dangerous_option",
                    "message": f"选项 '{opt_name}' 被标记为危险",
                    "severity": "medium",
                })
        else:
            arg_idx = i - arg_start
            arg = spec.get_argument(arg_idx)
            if arg and (arg.is_dangerous or arg.is_command):
                warnings.append({
                    "type": "dangerous_argument",
                    "message": f"参数位置 {arg_idx} ({arg.name}) 被标记为{'命令执行' if arg.is_command else '危险'}",
                    "severity": "medium",
                })

    return warnings
