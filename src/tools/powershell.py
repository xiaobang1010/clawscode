from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult

DANGEROUS_PATTERNS = [
    "remove-item -recurse -force c:\\",
    "remove-item -recurse -force /",
    "format-volume",
    "clear-disk",
    "stop-computer",
    "restart-computer",
    "invoke-expression",
    "iex ",
    "new-object system.net.webclient",
    "start-process -filepath cmd",
    "set-executionpolicy unrestricted",
    "invoke-webrequest | invoke-expression",
    "out-file -filepath c:\\windows",
    "set-content -path c:\\windows",
    "remove-windowsfeature",
    "uninstall-windowsfeature",
    "disable-firewall",
    "netsh advfirewall set allprofiles state off",
]


class PowerShellInput(BaseModel):
    command: str = Field(description="要执行的 PowerShell 命令")
    timeout: int = Field(default=120, description="超时秒数", ge=1, le=600)
    cwd: str | None = Field(default=None, description="工作目录")


class PowerShellTool(Tool):
    name = "PowerShell"
    description = "在 Windows 环境下执行 PowerShell 命令。非 Windows 环境不可用。"
    input_schema = PowerShellInput
    is_lazy = True

    def is_available(self) -> bool:
        return sys.platform == "win32"

    async def check_permissions(self, input: PowerShellInput, context: Any) -> Any:
        from src.tool import PermissionResult

        cmd_lower = input.command.lower().strip()
        for pattern in DANGEROUS_PATTERNS:
            if pattern in cmd_lower:
                return PermissionResult.DENY
        return PermissionResult.ASK

    async def call(self, input: PowerShellInput, context: Any) -> ToolResult:
        if sys.platform != "win32":
            return ToolResult(output="PowerShell 工具仅在 Windows 环境下可用", is_error=True)

        cmd_lower = input.command.lower().strip()
        for pattern in DANGEROUS_PATTERNS:
            if pattern in cmd_lower:
                return ToolResult(
                    output=f"拒绝执行危险命令: 包含被禁止的模式 '{pattern}'",
                    is_error=True,
                )

        work_dir = input.cwd or str(context.cwd)

        try:
            proc = await asyncio.create_subprocess_exec(
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                input.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=input.timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(
                output=f"命令超时 ({input.timeout}s): {input.command[:80]}",
                is_error=True,
            )
        except FileNotFoundError:
            return ToolResult(output="未找到 PowerShell 可执行文件", is_error=True)
        except OSError as e:
            return ToolResult(output=f"执行失败: {e}", is_error=True)

        output = stdout.decode(errors="replace")
        if proc.returncode != 0:
            err_output = stderr.decode(errors="replace")
            output += f"\nSTDERR: {err_output}"

        return ToolResult(
            output=output,
            is_error=proc.returncode != 0,
        )
