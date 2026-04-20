from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class TmuxError(Exception):
    pass


@dataclass
class TmuxSession:
    name: str
    id: str = ""
    windows: int = 0
    attached: bool = False
    created: str = ""


@dataclass
class TmuxPane:
    id: str
    session_name: str = ""
    window_index: int = 0
    pane_index: int = 0
    width: int = 80
    height: int = 24
    title: str = ""
    current_command: str = ""
    is_active: bool = False


@dataclass
class TmuxWindow:
    id: str
    name: str
    session_name: str = ""
    index: int = 0
    width: int = 80
    height: int = 24
    panes: list[TmuxPane] = field(default_factory=list)


class TmuxBackend:
    def __init__(self, socket_path: str | None = None) -> None:
        self._socket_path = socket_path
        self._tmux_bin: str | None = None

    def _get_tmux_bin(self) -> str:
        if self._tmux_bin is not None:
            return self._tmux_bin
        tmux = shutil.which("tmux")
        if tmux is None:
            raise TmuxError(
                "未找到 tmux。请安装 tmux：\n"
                "  Ubuntu/Debian: sudo apt install tmux\n"
                "  macOS: brew install tmux\n"
                "  Windows: 不支持 tmux（请使用 WSL）"
            )
        self._tmux_bin = tmux
        return self._tmux_bin

    def _base_args(self) -> list[str]:
        args = [self._get_tmux_bin()]
        if self._socket_path:
            args.extend(["-S", self._socket_path])
        return args

    async def _run_tmux(
        self,
        args: list[str],
        timeout: int = 10,
    ) -> str:
        cmd = self._base_args() + args
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TmuxError(f"tmux 命令超时: {' '.join(args)}")
        except FileNotFoundError:
            raise TmuxError("未找到 tmux 可执行文件")
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            if "no server running" in err_msg.lower() or "no sessions" in err_msg.lower():
                return ""
            raise TmuxError(f"tmux 命令失败: {err_msg or f'exit code {proc.returncode}'}")
        return stdout.decode("utf-8", errors="replace")

    async def is_available(self) -> bool:
        try:
            self._get_tmux_bin()
            return True
        except TmuxError:
            return False

    async def list_sessions(self) -> list[TmuxSession]:
        output = await self._run_tmux(
            ["list-sessions", "-F", "#{session_id}:#{session_name}:#{session_windows}:#{session_attached}"]
        )
        if not output.strip():
            return []
        sessions: list[TmuxSession] = []
        for line in output.strip().splitlines():
            parts = line.split(":", 3)
            if len(parts) < 4:
                continue
            sessions.append(
                TmuxSession(
                    id=parts[0],
                    name=parts[1],
                    windows=int(parts[2]),
                    attached=parts[3] == "1",
                )
            )
        return sessions

    async def has_session(self, name: str) -> bool:
        try:
            await self._run_tmux(["has-session", "-t", name])
            return True
        except TmuxError:
            return False

    async def new_session(
        self,
        name: str,
        command: str | None = None,
        detached: bool = True,
        width: int = 80,
        height: int = 24,
        working_dir: str | None = None,
    ) -> TmuxSession:
        args = ["new-session"]
        if detached:
            args.append("-d")
        args.extend(["-s", name])
        args.extend(["-x", str(width), "-y", str(height)])
        if working_dir:
            args.extend(["-c", working_dir])
        if command:
            args.append(command)
        await self._run_tmux(args)
        sessions = await self.list_sessions()
        for s in sessions:
            if s.name == name:
                return s
        return TmuxSession(name=name)

    async def kill_session(self, name: str) -> None:
        await self._run_tmux(["kill-session", "-t", name])

    async def rename_session(self, old_name: str, new_name: str) -> None:
        await self._run_tmux(["rename-session", "-t", old_name, new_name])

    async def list_windows(self, session: str) -> list[TmuxWindow]:
        output = await self._run_tmux(
            [
                "list-windows",
                "-t", session,
                "-F",
                "#{window_id}:#{window_name}:#{session_name}:#{window_index}:#{window_width}:#{window_height}",
            ]
        )
        if not output.strip():
            return []
        windows: list[TmuxWindow] = []
        for line in output.strip().splitlines():
            parts = line.split(":", 5)
            if len(parts) < 6:
                continue
            windows.append(
                TmuxWindow(
                    id=parts[0],
                    name=parts[1],
                    session_name=parts[2],
                    index=int(parts[3]),
                    width=int(parts[4]),
                    height=int(parts[5]),
                )
            )
        for w in windows:
            w.panes = await self.list_panes(session, w.index)
        return windows

    async def new_window(
        self,
        session: str,
        name: str | None = None,
        command: str | None = None,
        working_dir: str | None = None,
    ) -> TmuxWindow:
        args = ["new-window", "-t", session]
        if name:
            args.extend(["-n", name])
        if working_dir:
            args.extend(["-c", working_dir])
        if command:
            args.append(command)
        await self._run_tmux(args)
        windows = await self.list_windows(session)
        return windows[-1] if windows else TmuxWindow(id="", name=name or "")

    async def kill_window(self, session: str, window_index: int) -> None:
        await self._run_tmux(["kill-window", "-t", f"{session}:{window_index}"])

    async def list_panes(
        self,
        session: str,
        window_index: int | None = None,
    ) -> list[TmuxPane]:
        target = session
        if window_index is not None:
            target = f"{session}:{window_index}"
        output = await self._run_tmux(
            [
                "list-panes",
                "-t", target,
                "-F",
                "#{pane_id}:#{session_name}:#{window_index}:#{pane_index}:"
                "#{pane_width}:#{pane_height}:#{pane_title}:#{pane_current_command}:#{pane_active}",
            ]
        )
        if not output.strip():
            return []
        panes: list[TmuxPane] = []
        for line in output.strip().splitlines():
            parts = line.split(":", 8)
            if len(parts) < 9:
                continue
            panes.append(
                TmuxPane(
                    id=parts[0],
                    session_name=parts[1],
                    window_index=int(parts[2]),
                    pane_index=int(parts[3]),
                    width=int(parts[4]),
                    height=int(parts[5]),
                    title=parts[6],
                    current_command=parts[7],
                    is_active=parts[8] == "1",
                )
            )
        return panes

    async def split_pane(
        self,
        target: str,
        horizontal: bool = False,
        percentage: int | None = None,
        command: str | None = None,
        working_dir: str | None = None,
    ) -> TmuxPane:
        args = ["split-pane"]
        if horizontal:
            args.append("-h")
        else:
            args.append("-v")
        if percentage is not None:
            args.extend(["-p", str(percentage)])
        args.extend(["-t", target])
        if working_dir:
            args.extend(["-c", working_dir])
        if command:
            args.append(command)
        await self._run_tmux(args)
        session = target.split(":")[0] if ":" in target else target
        panes = await self.list_panes(session)
        return panes[-1] if panes else TmuxPane(id="")

    async def kill_pane(self, target: str) -> None:
        await self._run_tmux(["kill-pane", "-t", target])

    async def select_pane(self, target: str) -> None:
        await self._run_tmux(["select-pane", "-t", target])

    async def send_keys(
        self,
        target: str,
        keys: str,
        enter: bool = True,
    ) -> None:
        args = ["send-keys", "-t", target, keys]
        if enter:
            args.append("Enter")
        await self._run_tmux(args)

    async def send_keys_literal(
        self,
        target: str,
        keys: str,
    ) -> None:
        await self._run_tmux(["send-keys", "-t", target, "-l", keys])

    async def capture_pane(
        self,
        target: str,
        start_line: int | None = None,
        end_line: int | None = None,
        escape_sequences: bool = False,
    ) -> str:
        args = ["capture-pane", "-t", target, "-p"]
        if start_line is not None:
            args.extend(["-S", str(start_line)])
        if end_line is not None:
            args.extend(["-E", str(end_line)])
        if escape_sequences:
            args.append("-e")
        return await self._run_tmux(args)

    async def get_pane_output(self, target: str, scrollback: int = 1000) -> str:
        output = await self.capture_pane(target, start_line=-scrollback, end_line=-1)
        return output

    async def resize_pane(
        self,
        target: str,
        direction: str,
        amount: int = 5,
    ) -> None:
        if direction not in ("U", "D", "L", "R"):
            raise TmuxError(f"无效的调整方向: {direction}，有效值: U/D/L/R")
        await self._run_tmux(["resize-pane", "-t", target, f"-{direction}", str(amount)])

    async def set_layout(self, session: str, layout: str) -> None:
        if layout not in ("even-horizontal", "even-vertical", "main-horizontal", "main-vertical", "tiled"):
            raise TmuxError(f"无效的布局: {layout}")
        await self._run_tmux(["select-layout", "-t", session, layout])

    async def set_window_layout(self, target: str, layout: str) -> None:
        await self._run_tmux(["select-layout", "-t", target, layout])

    async def broadcast_keys(
        self,
        session: str,
        keys: str,
        enter: bool = True,
    ) -> None:
        windows = await self.list_windows(session)
        for window in windows:
            target = f"{session}:{window.index}"
            await self.send_keys(target, keys, enter=enter)

    async def pane_send_and_capture(
        self,
        target: str,
        command: str,
        wait: float = 0.5,
    ) -> str:
        await self.send_keys(target, command, enter=True)
        await asyncio.sleep(wait)
        return await self.capture_pane(target)

    async def sync_panes(self, session: str, on: bool = True) -> None:
        windows = await self.list_windows(session)
        for window in windows:
            target = f"{session}:{window.index}"
            if on:
                await self._run_tmux(["set-window-option", "-t", target, "synchronize-panes", "on"])
            else:
                await self._run_tmux(["set-window-option", "-t", target, "synchronize-panes", "off"])


_tmux_backend: TmuxBackend | None = None


def get_tmux_backend() -> TmuxBackend:
    global _tmux_backend
    if _tmux_backend is None:
        _tmux_backend = TmuxBackend()
    return _tmux_backend


def set_tmux_backend(backend: TmuxBackend) -> None:
    global _tmux_backend
    _tmux_backend = backend
