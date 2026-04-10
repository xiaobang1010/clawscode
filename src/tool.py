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


class Tool(ABC):
    name: str
    description: str
    input_schema: type[BaseModel]

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
