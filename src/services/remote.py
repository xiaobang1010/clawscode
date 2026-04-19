from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)


class RemoteError(Exception):
    pass


@dataclass
class SSHConfig:
    host: str
    port: int = 22
    username: str | None = None
    password: str | None = None
    key_path: str | None = None
    key_passphrase: str | None = None
    known_hosts_path: str | None = None
    connect_timeout: int = 30
    keepalive_interval: int = 30


@dataclass
class RemoteCommandResult:
    exit_code: int
    stdout: str
    stderr: str
    elapsed: float = 0.0


@dataclass
class RemoteFileInfo:
    path: str
    name: str
    is_dir: bool
    size: int = 0
    modified: str = ""
    permissions: str = ""


class RemoteService:
    def __init__(self) -> None:
        self._connections: dict[str, Any] = {}
        self._configs: dict[str, SSHConfig] = {}
        self._lock = asyncio.Lock()

    @property
    def connected_hosts(self) -> list[str]:
        return [name for name, conn in self._connections.items() if conn is not None]

    async def connect(self, name: str, config: SSHConfig) -> None:
        async with self._lock:
            if name in self._connections and self._connections[name] is not None:
                logger.info("SSH 连接 '%s' 已存在，先断开旧连接", name)
                await self._disconnect_internal(name)
            try:
                import asyncssh
            except ImportError:
                raise RemoteError(
                    "需要安装 asyncssh 库：pip install asyncssh"
                )
            connect_kwargs: dict[str, Any] = {
                "host": config.host,
                "port": config.port,
                "connect_timeout": config.connect_timeout,
                "keepalive_interval": config.keepalive_interval,
            }
            if config.username:
                connect_kwargs["username"] = config.username
            if config.password:
                connect_kwargs["password"] = config.password
            if config.key_path:
                connect_kwargs["client_keys"] = [config.key_path]
                if config.key_passphrase:
                    connect_kwargs["passphrase"] = config.key_passphrase
            if config.known_hosts_path:
                connect_kwargs["known_hosts"] = config.known_hosts_path
            else:
                connect_kwargs["known_hosts"] = None
            try:
                conn = await asyncssh.connect(**connect_kwargs)
            except Exception as e:
                raise RemoteError(f"SSH 连接 {config.host}:{config.port} 失败: {e}")
            self._connections[name] = conn
            self._configs[name] = config
            logger.info("SSH 连接 '%s' (%s:%d) 已建立", name, config.host, config.port)

    async def disconnect(self, name: str) -> None:
        async with self._lock:
            await self._disconnect_internal(name)

    async def _disconnect_internal(self, name: str) -> None:
        conn = self._connections.pop(name, None)
        self._configs.pop(name, None)
        if conn is not None:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:
                pass
            logger.info("SSH 连接 '%s' 已断开", name)

    async def disconnect_all(self) -> None:
        async with self._lock:
            names = list(self._connections.keys())
            for name in names:
                await self._disconnect_internal(name)

    def _get_connection(self, name: str) -> Any:
        conn = self._connections.get(name)
        if conn is None:
            raise RemoteError(f"SSH 连接 '{name}' 不存在或已断开")
        return conn

    async def execute(
        self,
        name: str,
        command: str,
        timeout: int | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> RemoteCommandResult:
        import time

        conn = self._get_connection(name)
        if cwd:
            command = f"cd {cwd} && ({command})"
        if env:
            env_prefix = " ".join(f"{k}={v}" for k, v in env.items())
            command = f"env {env_prefix} {command}"
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                conn.run(command, check=False),
                timeout=timeout or 300,
            )
        except asyncio.TimeoutError:
            raise RemoteError(f"远程命令执行超时 ({timeout or 300}s): {command[:100]}")
        except Exception as e:
            raise RemoteError(f"远程命令执行失败: {e}")
        elapsed = time.monotonic() - start
        return RemoteCommandResult(
            exit_code=result.exit_status,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            elapsed=elapsed,
        )

    async def execute_streaming(
        self,
        name: str,
        command: str,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> AsyncIterator[bytes]:
        conn = self._get_connection(name)
        if cwd:
            command = f"cd {cwd} && ({command})"
        try:
            async with conn.create_process(command) as proc:
                async for data in proc.stdout:
                    yield data.encode() if isinstance(data, str) else data
        except Exception as e:
            raise RemoteError(f"远程流式命令执行失败: {e}")

    async def read_file(self, name: str, remote_path: str) -> str:
        conn = self._get_connection(name)
        try:
            async with conn.start_sftp_client() as sftp:
                async with sftp.open(remote_path, "r") as f:
                    content = await f.read()
                    if isinstance(content, bytes):
                        return content.decode("utf-8", errors="replace")
                    return content
        except FileNotFoundError:
            raise RemoteError(f"远程文件不存在: {remote_path}")
        except Exception as e:
            raise RemoteError(f"读取远程文件失败: {e}")

    async def write_file(
        self,
        name: str,
        remote_path: str,
        content: str,
        create_dirs: bool = True,
    ) -> None:
        conn = self._get_connection(name)
        try:
            async with conn.start_sftp_client() as sftp:
                if create_dirs:
                    parent = str(PurePosixPath(remote_path).parent)
                    try:
                        await sftp.stat(parent)
                    except FileNotFoundError:
                        await self._mkdirs_remote(sftp, parent)
                async with sftp.open(remote_path, "w") as f:
                    await f.write(content)
        except Exception as e:
            raise RemoteError(f"写入远程文件失败: {e}")

    async def _mkdirs_remote(self, sftp: Any, path: str) -> None:
        parts = PurePosixPath(path).parts
        current = ""
        for part in parts:
            if not part or part == "/":
                current = "/"
                continue
            current = str(PurePosixPath(current) / part) if current != "/" else f"/{part}"
            try:
                await sftp.stat(current)
            except FileNotFoundError:
                try:
                    await sftp.mkdir(current)
                except Exception:
                    pass

    async def list_dir(self, name: str, remote_path: str) -> list[RemoteFileInfo]:
        conn = self._get_connection(name)
        try:
            async with conn.start_sftp_client() as sftp:
                entries = await sftp.readdir(remote_path)
                result: list[RemoteFileInfo] = []
                for entry in entries:
                    attrs = entry.attrs
                    full_path = str(PurePosixPath(remote_path) / entry.filename)
                    result.append(
                        RemoteFileInfo(
                            path=full_path,
                            name=entry.filename,
                            is_dir=bool(attrs.isDirectory()) if hasattr(attrs, "isDirectory") else False,
                            size=attrs.size or 0,
                            modified=str(attrs.mtime) if attrs.mtime else "",
                            permissions=attrs.permissions or "",
                        )
                    )
                return result
        except Exception as e:
            raise RemoteError(f"列出远程目录失败: {e}")

    async def stat(self, name: str, remote_path: str) -> RemoteFileInfo:
        conn = self._get_connection(name)
        try:
            async with conn.start_sftp_client() as sftp:
                attrs = await sftp.stat(remote_path)
                filename = PurePosixPath(remote_path).name
                return RemoteFileInfo(
                    path=remote_path,
                    name=filename,
                    is_dir=bool(attrs.isDirectory()) if hasattr(attrs, "isDirectory") else False,
                    size=attrs.size or 0,
                    modified=str(attrs.mtime) if attrs.mtime else "",
                    permissions=attrs.permissions or "",
                )
        except FileNotFoundError:
            raise RemoteError(f"远程路径不存在: {remote_path}")
        except Exception as e:
            raise RemoteError(f"获取远程文件信息失败: {e}")

    async def delete_file(self, name: str, remote_path: str) -> None:
        conn = self._get_connection(name)
        try:
            async with conn.start_sftp_client() as sftp:
                await sftp.remove(remote_path)
        except FileNotFoundError:
            raise RemoteError(f"远程文件不存在: {remote_path}")
        except Exception as e:
            raise RemoteError(f"删除远程文件失败: {e}")

    async def mkdir(self, name: str, remote_path: str, parents: bool = True) -> None:
        conn = self._get_connection(name)
        try:
            async with conn.start_sftp_client() as sftp:
                if parents:
                    await self._mkdirs_remote(sftp, remote_path)
                else:
                    await sftp.mkdir(remote_path)
        except Exception as e:
            raise RemoteError(f"创建远程目录失败: {e}")

    async def download_file(
        self, name: str, remote_path: str, local_path: str
    ) -> None:
        conn = self._get_connection(name)
        try:
            async with conn.start_sftp_client() as sftp:
                await sftp.get(remote_path, local_path)
        except FileNotFoundError:
            raise RemoteError(f"远程文件不存在: {remote_path}")
        except Exception as e:
            raise RemoteError(f"下载远程文件失败: {e}")

    async def upload_file(
        self, name: str, local_path: str, remote_path: str
    ) -> None:
        conn = self._get_connection(name)
        try:
            async with conn.start_sftp_client() as sftp:
                await sftp.put(local_path, remote_path)
        except FileNotFoundError:
            raise RemoteError(f"本地文件不存在: {local_path}")
        except Exception as e:
            raise RemoteError(f"上传文件失败: {e}")

    async def is_connected(self, name: str) -> bool:
        conn = self._connections.get(name)
        if conn is None:
            return False
        try:
            result = await asyncio.wait_for(
                conn.run("echo ok", check=False),
                timeout=10,
            )
            return result.exit_status == 0
        except Exception:
            return False

    async def reconnect(self, name: str) -> None:
        config = self._configs.get(name)
        if config is None:
            raise RemoteError(f"找不到连接 '{name}' 的配置信息，无法重连")
        async with self._lock:
            await self._disconnect_internal(name)
        await self.connect(name, config)


from typing import AsyncIterator

_remote_service: RemoteService | None = None


def get_remote_service() -> RemoteService:
    global _remote_service
    if _remote_service is None:
        _remote_service = RemoteService()
    return _remote_service


def set_remote_service(service: RemoteService) -> None:
    global _remote_service
    _remote_service = service
