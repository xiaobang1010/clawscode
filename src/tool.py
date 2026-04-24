from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel


class PermissionResult(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class ToolResult(BaseModel):
    output: str
    error: str | None = None
    is_error: bool = False
    metadata: dict = {}
    structured_output: dict | None = None

    def truncate(self, max_chars: int = 25000) -> ToolResult:
        if len(self.output) > max_chars:
            truncated = self.output[:max_chars] + f"\n...[truncated, showed {max_chars} of {len(self.output)} chars]"
            return ToolResult(output=truncated, error=self.error, is_error=self.is_error, structured_output=self.structured_output)
        return self

    @classmethod
    def from_output(cls, output: str, max_chars: int = 25000) -> ToolResult:
        result = cls(output=output)
        return result.truncate(max_chars)


def truncate_output(output: str, max_chars: int = 25000) -> str:
    if len(output) > max_chars:
        return output[:max_chars] + f"\n...[truncated, showed {max_chars} of {len(output)} chars]"
    return output


class Tool(ABC):
    name: str
    description: str
    input_schema: type[BaseModel]
    user_facing_name: str = ""
    is_readonly: bool = False
    max_result_size_chars: int = 25000
    is_lazy: bool = False
    output_schema: type[BaseModel] | None = None
    aliases: list[str] = []
    search_hint: str = ""
    interrupt_behavior: str = "cancel"

    @abstractmethod
    async def call(self, input: BaseModel, context: Any) -> ToolResult:
        ...

    async def check_permissions(self, input: BaseModel, context: Any) -> PermissionResult:
        return PermissionResult.ASK

    async def validate_input(self, input: dict) -> dict:
        return input

    def get_json_schema(self) -> dict:
        return self.input_schema.model_json_schema()

    def get_openai_tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema.model_json_schema(),
            },
        }

    def get_user_facing_name(self) -> str:
        return self.user_facing_name or self.name

    def is_read_only(self) -> bool:
        return self.is_readonly

    def is_available(self) -> bool:
        return True

    def is_concurrency_safe(self, input: BaseModel) -> bool:
        return False

    def is_destructive(self, input: BaseModel) -> bool:
        return False
