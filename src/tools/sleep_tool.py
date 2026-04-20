from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class SleepInput(BaseModel):
    seconds: float = Field(description="等待秒数", ge=0.1, le=300)


class SleepTool(Tool):
    name = "Sleep"
    description = "暂停执行指定秒数"
    input_schema = SleepInput
    is_readonly = True

    async def call(self, input: SleepInput, context: Any) -> ToolResult:
        await asyncio.sleep(input.seconds)
        return ToolResult(output=f"已等待 {input.seconds} 秒")
