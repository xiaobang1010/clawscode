from __future__ import annotations

import sys
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class QuestionOption(BaseModel):
    label: str = Field(description="选项显示文本")
    description: str = Field(default="", description="选项描述说明")


class AskUserQuestionInput(BaseModel):
    question: str = Field(description="要向用户提出的问题")
    header: str = Field(default="", description="问题的简短标签，最多12个字符")
    options: list[QuestionOption] = Field(default_factory=list, description="2-4个选项")
    multiSelect: bool = Field(default=False, description="是否允许多选")


class AskUserQuestionTool(Tool):
    name = "AskUserQuestion"
    description = "向用户提出结构化问题，支持选项选择。用于需要用户确认或选择时。"
    input_schema = AskUserQuestionInput

    async def call(self, input: AskUserQuestionInput, context: Any) -> ToolResult:
        lines = []
        if input.header:
            lines.append(f"[{input.header}]")
        lines.append(input.question)

        valid_options = []
        if input.options:
            valid_options = input.options[:4]
            for i, opt in enumerate(valid_options, 1):
                line = f"  {i}. {opt.label}"
                if opt.description:
                    line += f" — {opt.description}"
                lines.append(line)
            lines.append(f"  {'(可多选)' if input.multiSelect else '(单选)'}")
            lines.append("  0. 自定义输入")

        prompt_text = "\n".join(lines) + "\n\n请选择: "
        sys.stdout.write(prompt_text)
        sys.stdout.flush()

        try:
            answer = sys.stdin.readline().rstrip("\n")
        except (EOFError, KeyboardInterrupt):
            return ToolResult(output="用户取消了操作", is_error=True)

        if valid_options:
            if answer == "0":
                return ToolResult(output=f"用户自定义输入: {answer}")

            try:
                selected_idx = int(answer) - 1
                if 0 <= selected_idx < len(valid_options):
                    selected = valid_options[selected_idx]
                    return ToolResult(output=f"用户选择了: {selected.label}")
            except ValueError:
                pass

            for opt in valid_options:
                if answer.lower() == opt.label.lower():
                    return ToolResult(output=f"用户选择了: {opt.label}")

            return ToolResult(output=f"用户输入: {answer}")
        else:
            return ToolResult(output=f"用户回答: {answer}")
