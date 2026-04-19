from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BridgeError(Exception):
    pass


class BridgeStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class MessageDirection(str, Enum):
    LOCAL_TO_REMOTE = "local_to_remote"
    REMOTE_TO_LOCAL = "remote_to_local"


@dataclass
class BridgeMessage:
    id: str
    direction: MessageDirection
    payload: str
    timestamp: float = field(default_factory=time.time)
    source: str = ""
    target: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BridgeConfig:
    name: str
    remote_host: str
    remote_port: int = 22
    username: str | None = None
    remote_working_dir: str | None = None
    auto_reconnect: bool = True
    reconnect_interval: int = 5
    max_reconnect_attempts: int = 10
    message_buffer_size: int = 1000
    sync_files: list[str] = field(default_factory=list)


@dataclass
class BridgeStats:
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    last_activity: float = 0.0
    connected_since: float = 0.0
    reconnect_count: int = 0


class Bridge:
    def __init__(self, config: BridgeConfig) -> None:
        self._config = config
        self._status = BridgeStatus.DISCONNECTED
        self._message_queue: asyncio.Queue[BridgeMessage] = asyncio.Queue(
            maxsize=config.message_buffer_size
        )
        self._history: list[BridgeMessage] = []
        self._stats = BridgeStats()
        self._listeners: list[asyncio.Queue[BridgeMessage]] = []
        self._reconnect_task: asyncio.Task | None = None
        self._forward_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._bridge_id = str(uuid.uuid4())[:8]

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def status(self) -> BridgeStatus:
        return self._status

    @property
    def stats(self) -> BridgeStats:
        return self._stats

    @property
    def config(self) -> BridgeConfig:
        return self._config

    @property
    def is_connected(self) -> bool:
        return self._status == BridgeStatus.CONNECTED

    async def connect(self) -> None:
        if self._status == BridgeStatus.CONNECTED:
            return
        self._status = BridgeStatus.CONNECTING
        try:
            from src.services.remote import SSHConfig, get_remote_service

            remote = get_remote_service()
            ssh_config = SSHConfig(
                host=self._config.remote_host,
                port=self._config.remote_port,
                username=self._config.username,
            )
            await remote.connect(self._config.name, ssh_config)
            self._status = BridgeStatus.CONNECTED
            self._stats.connected_since = time.time()
            self._forward_task = asyncio.create_task(self._forward_loop())
            logger.info("Bridge '%s' 已连接到 %s", self._config.name, self._config.remote_host)
        except Exception as e:
            self._status = BridgeStatus.ERROR
            raise BridgeError(f"Bridge 连接失败: {e}")

    async def disconnect(self) -> None:
        self._status = BridgeStatus.DISCONNECTED
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
        if self._forward_task:
            self._forward_task.cancel()
            try:
                await self._forward_task
            except asyncio.CancelledError:
                pass
            self._forward_task = None
        try:
            from src.services.remote import get_remote_service

            remote = get_remote_service()
            await remote.disconnect(self._config.name)
        except Exception:
            pass
        logger.info("Bridge '%s' 已断开", self._config.name)

    async def send_to_remote(
        self,
        payload: str,
        source: str = "local",
        target: str = "remote",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not self.is_connected:
            raise BridgeError(f"Bridge '{self._config.name}' 未连接")
        msg_id = str(uuid.uuid4())[:8]
        msg = BridgeMessage(
            id=msg_id,
            direction=MessageDirection.LOCAL_TO_REMOTE,
            payload=payload,
            source=source,
            target=target,
            metadata=metadata or {},
        )
        await self._enqueue(msg)
        try:
            from src.services.remote import get_remote_service

            remote = get_remote_service()
            cwd = self._config.remote_working_dir
            result = await remote.execute(self._config.name, payload, cwd=cwd)
            response_msg = BridgeMessage(
                id=msg_id,
                direction=MessageDirection.REMOTE_TO_LOCAL,
                payload=result.stdout,
                source="remote",
                target=source,
                metadata={
                    "exit_code": result.exit_code,
                    "stderr": result.stderr,
                    "elapsed": result.elapsed,
                },
            )
            await self._enqueue(response_msg)
            self._stats.messages_received += 1
            self._stats.bytes_received += len(result.stdout)
        except Exception as e:
            error_msg = BridgeMessage(
                id=msg_id,
                direction=MessageDirection.REMOTE_TO_LOCAL,
                payload=str(e),
                source="remote",
                target=source,
                metadata={"error": True},
            )
            await self._enqueue(error_msg)
            raise BridgeError(f"远程执行失败: {e}")
        self._stats.messages_sent += 1
        self._stats.bytes_sent += len(payload)
        self._stats.last_activity = time.time()
        return result.stdout

    async def send_file_to_remote(
        self, local_path: str, remote_path: str
    ) -> None:
        if not self.is_connected:
            raise BridgeError(f"Bridge '{self._config.name}' 未连接")
        try:
            from src.services.remote import get_remote_service

            remote = get_remote_service()
            await remote.upload_file(self._config.name, local_path, remote_path)
            self._stats.last_activity = time.time()
            logger.info("Bridge '%s': 文件已上传 %s -> %s", self._config.name, local_path, remote_path)
        except Exception as e:
            raise BridgeError(f"文件上传失败: {e}")

    async def fetch_file_from_remote(
        self, remote_path: str, local_path: str
    ) -> None:
        if not self.is_connected:
            raise BridgeError(f"Bridge '{self._config.name}' 未连接")
        try:
            from src.services.remote import get_remote_service

            remote = get_remote_service()
            await remote.download_file(self._config.name, remote_path, local_path)
            self._stats.last_activity = time.time()
            logger.info("Bridge '%s': 文件已下载 %s -> %s", self._config.name, remote_path, local_path)
        except Exception as e:
            raise BridgeError(f"文件下载失败: {e}")

    async def sync_files(self) -> list[str]:
        if not self._config.sync_files:
            return []
        synced: list[str] = []
        for file_pattern in self._config.sync_files:
            try:
                local_path = file_pattern
                remote_path = file_pattern
                if self._config.remote_working_dir:
                    import os
                    remote_path = os.path.join(self._config.remote_working_dir, file_pattern)
                await self.send_file_to_remote(local_path, remote_path)
                synced.append(file_pattern)
            except Exception as e:
                logger.warning("Bridge '%s': 同步文件 %s 失败: %s", self._config.name, file_pattern, e)
        return synced

    def subscribe(self) -> asyncio.Queue[BridgeMessage]:
        q: asyncio.Queue[BridgeMessage] = asyncio.Queue()
        self._listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[BridgeMessage]) -> None:
        if q in self._listeners:
            self._listeners.remove(q)

    def get_history(
        self,
        limit: int = 100,
        direction: MessageDirection | None = None,
    ) -> list[BridgeMessage]:
        messages = self._history
        if direction:
            messages = [m for m in messages if m.direction == direction]
        return messages[-limit:]

    async def _enqueue(self, msg: BridgeMessage) -> None:
        self._history.append(msg)
        if len(self._history) > self._config.message_buffer_size:
            self._history = self._history[-self._config.message_buffer_size:]
        for listener in self._listeners:
            try:
                listener.put_nowait(msg)
            except asyncio.QueueFull:
                pass
        try:
            self._message_queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass

    async def _forward_loop(self) -> None:
        try:
            while self._status == BridgeStatus.CONNECTED:
                await asyncio.sleep(1)
                try:
                    from src.services.remote import get_remote_service

                    remote = get_remote_service()
                    if not await remote.is_connected(self._config.name):
                        logger.warning("Bridge '%s': SSH 连接丢失", self._config.name)
                        if self._config.auto_reconnect:
                            self._status = BridgeStatus.RECONNECTING
                            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
                        else:
                            self._status = BridgeStatus.ERROR
                        break
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass

    async def _reconnect_loop(self) -> None:
        self._stats.reconnect_count += 1
        attempts = 0
        while attempts < self._config.max_reconnect_attempts:
            attempts += 1
            logger.info(
                "Bridge '%s': 重连尝试 %d/%d",
                self._config.name, attempts, self._config.max_reconnect_attempts,
            )
            try:
                from src.services.remote import get_remote_service

                remote = get_remote_service()
                await remote.reconnect(self._config.name)
                self._status = BridgeStatus.CONNECTED
                self._stats.connected_since = time.time()
                self._forward_task = asyncio.create_task(self._forward_loop())
                logger.info("Bridge '%s': 重连成功", self._config.name)
                return
            except Exception as e:
                logger.warning("Bridge '%s': 重连失败: %s", self._config.name, e)
                await asyncio.sleep(self._config.reconnect_interval)
        self._status = BridgeStatus.ERROR
        logger.error("Bridge '%s': 超过最大重连次数", self._config.name)


class BridgeManager:
    def __init__(self) -> None:
        self._bridges: dict[str, Bridge] = {}
        self._lock = asyncio.Lock()

    async def create_bridge(self, config: BridgeConfig) -> Bridge:
        async with self._lock:
            if config.name in self._bridges:
                raise BridgeError(f"Bridge '{config.name}' 已存在")
            bridge = Bridge(config)
            self._bridges[config.name] = bridge
            return bridge

    async def remove_bridge(self, name: str) -> None:
        async with self._lock:
            bridge = self._bridges.pop(name, None)
            if bridge:
                await bridge.disconnect()

    def get_bridge(self, name: str) -> Bridge | None:
        return self._bridges.get(name)

    def list_bridges(self) -> list[Bridge]:
        return list(self._bridges.values())

    async def connect_all(self) -> None:
        for bridge in self._bridges.values():
            if bridge.status == BridgeStatus.DISCONNECTED:
                try:
                    await bridge.connect()
                except Exception as e:
                    logger.error("Bridge '%s' 连接失败: %s", bridge.name, e)

    async def disconnect_all(self) -> None:
        for bridge in self._bridges.values():
            try:
                await bridge.disconnect()
            except Exception as e:
                logger.error("Bridge '%s' 断开失败: %s", bridge.name, e)


_bridge_manager: BridgeManager | None = None


def get_bridge_manager() -> BridgeManager:
    global _bridge_manager
    if _bridge_manager is None:
        _bridge_manager = BridgeManager()
    return _bridge_manager


def set_bridge_manager(manager: BridgeManager) -> None:
    global _bridge_manager
    _bridge_manager = manager
