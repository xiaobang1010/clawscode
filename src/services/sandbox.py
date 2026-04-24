from __future__ import annotations

import logging
import os
import platform
import shutil
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ISandboxManager(Protocol):
    def initialize(self) -> bool: ...
    def is_supported_platform(self) -> bool: ...
    def is_sandboxing_enabled(self) -> bool: ...
    def wrap_with_sandbox(self, command: str, config: SandboxRuntimeConfig) -> str: ...
    def cleanup(self) -> None: ...
    def reset(self) -> None: ...


@dataclass
class SandboxRuntimeConfig:
    project_dir: str = ""
    allowed_write_dirs: list[str] = field(default_factory=list)
    denied_write_dirs: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    denied_domains: list[str] = field(default_factory=list)
    network_enabled: bool = True
    dangerously_disable: bool = False

    PROTECTED_WRITE_PATHS = [
        "settings.json",
        ".clawscode/skills",
    ]

    def is_protected_path(self, path: str) -> bool:
        for protected in self.PROTECTED_WRITE_PATHS:
            if path.endswith(protected) or protected in path:
                return True
        return False


class SandboxManager:
    def __init__(self) -> None:
        self._initialized = False
        self._bwrap_path: str | None = None
        self._enabled = False

    def initialize(self) -> bool:
        if self._initialized:
            return self._enabled

        self._initialized = True

        if not self.is_supported_platform():
            logger.info("沙箱: 平台不支持")
            return False

        self._bwrap_path = shutil.which("bwrap")
        if self._bwrap_path is None:
            logger.info("沙箱: bwrap 未安装")
            return False

        self._enabled = True
        logger.info("沙箱: 已初始化")
        return True

    def is_supported_platform(self) -> bool:
        system = platform.system().lower()
        if system == "linux":
            return True
        if system == "darwin":
            return True

        if "microsoft" in platform.uname().release.lower():
            try:
                major = int(platform.uname().release.split("-")[0].split(".")[0])
                if major >= 5:
                    return True
            except (ValueError, IndexError):
                pass
            return False

        return False

    def is_sandboxing_enabled(self) -> bool:
        if os.environ.get("CLAWSCODE_DISABLE_SANDBOX"):
            return False
        return self._enabled and self._bwrap_path is not None

    def wrap_with_sandbox(self, command: str, config: SandboxRuntimeConfig) -> str:
        if config.dangerously_disable:
            return command

        if not self.is_sandboxing_enabled():
            return command

        if not config.project_dir:
            return command

        bwrap_args = self._build_bwrap_args(config)
        return f"{self._bwrap_path} {' '.join(bwrap_args)} {command}"

    def _build_bwrap_args(self, config: SandboxRuntimeConfig) -> list[str]:
        args = [
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/sbin", "/sbin",
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
        ]

        args.extend(["--bind", config.project_dir, config.project_dir])

        for d in config.allowed_write_dirs:
            args.extend(["--bind", d, d])

        for protected in config.PROTECTED_WRITE_PATHS:
            args.extend(["--ro-bind-try", protected, protected])

        if not config.network_enabled:
            args.append("--unshare-net")

        return args

    def cleanup(self) -> None:
        pass

    def reset(self) -> None:
        self._initialized = False
        self._enabled = False
        self._bwrap_path = None


_sandbox_instance: SandboxManager | None = None


def get_sandbox_manager() -> SandboxManager:
    global _sandbox_instance
    if _sandbox_instance is None:
        _sandbox_instance = SandboxManager()
        _sandbox_instance.initialize()
    return _sandbox_instance


def should_use_sandbox(config: SandboxRuntimeConfig) -> bool:
    manager = get_sandbox_manager()
    return manager.is_sandboxing_enabled() and not config.dangerously_disable
