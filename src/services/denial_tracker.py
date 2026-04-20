from __future__ import annotations

from dataclasses import dataclass

from src.permissions import PermissionChecker, PermissionMode


@dataclass
class DenialRecord:
    tool_name: str
    rule: str
    consecutive_count: int


class DenialTracker:
    def __init__(self, max_consecutive_denials: int = 3):
        self._max_consecutive = max_consecutive_denials
        self._denial_counts: dict[str, int] = {}
        self._total_denials: int = 0
        self._records: list[DenialRecord] = []

    def record_denial(self, tool_name: str, rule: str = "") -> None:
        key = tool_name
        self._denial_counts[key] = self._denial_counts.get(key, 0) + 1
        self._total_denials += 1
        self._records.append(DenialRecord(
            tool_name=tool_name,
            rule=rule,
            consecutive_count=self._denial_counts[key],
        ))

    def reset_for_tool(self, tool_name: str) -> None:
        self._denial_counts.pop(tool_name, None)

    def get_consecutive_denials(self, tool_name: str) -> int:
        return self._denial_counts.get(tool_name, 0)

    def should_downgrade(self, tool_name: str) -> bool:
        return self.get_consecutive_denials(tool_name) >= self._max_consecutive

    def check_and_downgrade(self, permission_checker: PermissionChecker) -> bool:
        downgraded = False
        for tool_name, count in list(self._denial_counts.items()):
            if count >= self._max_consecutive:
                current = permission_checker.mode
                if current == PermissionMode.BYPASS:
                    permission_checker.set_mode(PermissionMode.DEFAULT)
                    downgraded = True
                elif current == PermissionMode.AUTO:
                    permission_checker.set_mode(PermissionMode.DEFAULT)
                    downgraded = True
                elif current == PermissionMode.DEFAULT:
                    permission_checker.set_mode(PermissionMode.PLAN)
                    downgraded = True
                self.reset_for_tool(tool_name)
        return downgraded

    @property
    def total_denials(self) -> int:
        return self._total_denials

    def get_summary(self) -> str:
        if not self._denial_counts:
            return "无拒绝记录"
        parts = [f"总拒绝次数: {self._total_denials}"]
        for tool, count in self._denial_counts.items():
            parts.append(f"  {tool}: {count} 次")
        return "\n".join(parts)
