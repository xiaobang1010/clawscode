from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class WorkflowInput(BaseModel):
    steps: list[dict[str, Any]] = Field(
        description="工作流步骤列表。每个步骤包含 tool、input 字段，可选 condition、id 字段。"
    )
    stop_on_error: bool = Field(default=True, description="步骤失败时是否停止")
    max_steps: int = Field(default=50, description="最大步骤数", ge=1, le=200)


class WorkflowTool(Tool):
    name = "Workflow"
    description = "执行工作流脚本。支持步骤序列执行和条件分支。"
    input_schema = WorkflowInput

    async def call(self, input: WorkflowInput, context: Any) -> ToolResult:
        steps = input.steps[:input.max_steps]
        if not steps:
            return ToolResult(output="无工作流步骤", is_error=True)

        results: list[dict[str, Any]] = []
        step_vars: dict[str, Any] = {}
        completed = 0
        failed = 0
        skipped = 0

        for i, step in enumerate(steps):
            step_id = step.get("id", f"step_{i}")
            tool_name = step.get("tool", "")
            tool_input = step.get("input", {})
            condition = step.get("condition")

            if condition is not None:
                cond_result = _evaluate_condition(condition, step_vars, results)
                if not cond_result:
                    skipped += 1
                    results.append({
                        "id": step_id,
                        "status": "skipped",
                        "reason": "condition not met",
                    })
                    continue

            if not tool_name:
                failed += 1
                results.append({
                    "id": step_id,
                    "status": "error",
                    "error": "missing tool name",
                })
                if input.stop_on_error:
                    break
                continue

            tool_result = await _execute_step(tool_name, tool_input, context)

            status = "completed" if not tool_result.is_error else "failed"
            if status == "completed":
                completed += 1
            else:
                failed += 1

            step_vars[step_id] = {
                "output": tool_result.output[:500],
                "is_error": tool_result.is_error,
            }

            results.append({
                "id": step_id,
                "tool": tool_name,
                "status": status,
                "output": tool_result.output[:300],
            })

            if tool_result.is_error and input.stop_on_error:
                break

        summary = (
            f"工作流完成: {completed} 成功, {failed} 失败, {skipped} 跳过 "
            f"(共 {len(steps)} 步)"
        )
        detail_lines = [summary, ""]
        for r in results:
            status_icon = {"completed": "+", "failed": "x", "skipped": "-", "error": "!"}.get(
                r["status"], "?"
            )
            line = f"  [{status_icon}] {r['id']}: {r['status']}"
            if r.get("tool"):
                line += f" ({r['tool']})"
            if r.get("error"):
                line += f" - {r['error']}"
            elif r.get("output"):
                preview = r["output"].replace("\n", " ")[:60]
                line += f" - {preview}"
            detail_lines.append(line)

        return ToolResult(
            output="\n".join(detail_lines),
            is_error=failed > 0,
        )


def _evaluate_condition(condition: Any, variables: dict, results: list[dict]) -> bool:
    if isinstance(condition, bool):
        return condition
    if isinstance(condition, str):
        if condition.startswith("$"):
            var_name = condition[1:]
            var = variables.get(var_name)
            if var is None:
                return False
            return not var.get("is_error", True)
        return bool(condition)
    if isinstance(condition, dict):
        op = condition.get("op", condition.get("operator", ""))
        left = condition.get("left", condition.get("variable", ""))
        right = condition.get("right", condition.get("value", ""))

        if left.startswith("$"):
            var_name = left[1:]
            var = variables.get(var_name, {})
            left_val = var.get("output", "")
        else:
            left_val = left

        if op in ("eq", "==", "equals"):
            return str(left_val) == str(right)
        if op in ("ne", "!=", "not_equals"):
            return str(left_val) != str(right)
        if op in ("contains", "in"):
            return str(right) in str(left_val)
        if op in ("not_contains", "not_in"):
            return str(right) not in str(left_val)
        if op in ("success", "succeeded"):
            var = variables.get(left.lstrip("$"), {})
            return not var.get("is_error", True)
        if op in ("failed", "failure"):
            var = variables.get(left.lstrip("$"), {})
            return var.get("is_error", False)

    return bool(condition)


async def _execute_step(tool_name: str, tool_input: dict, context: Any) -> ToolResult:
    available_tools: dict[str, Any] = {}
    if hasattr(context, "tools"):
        for tool in context.tools:
            if hasattr(tool, "name"):
                available_tools[tool.name] = tool

    tool = available_tools.get(tool_name)
    if tool is None:
        return ToolResult(output=f"工具未找到: {tool_name}", is_error=True)

    try:
        schema_cls = tool.input_schema
        validated = schema_cls(**tool_input)
        return await tool.call(validated, context)
    except Exception as e:
        return ToolResult(output=f"步骤执行失败: {e}", is_error=True)
