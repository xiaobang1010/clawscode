from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class NotebookEditInput(BaseModel):
    notebook_path: str = Field(description="Notebook 文件路径 (.ipynb)")
    operation: str = Field(description="操作类型: add_cell, delete_cell, edit_cell, read")
    cell_index: int | None = Field(default=None, description="单元格索引（从 0 开始）")
    cell_type: str | None = Field(default=None, description="单元格类型: code, markdown")
    source: str | None = Field(default=None, description="单元格内容")
    cell_id: str | None = Field(default=None, description="单元格 ID（可选）")


class NotebookEditTool(Tool):
    name = "NotebookEdit"
    description = "编辑 Jupyter Notebook (.ipynb) 文件。支持读取、添加、删除和编辑单元格。"
    input_schema = NotebookEditInput

    async def call(self, input: NotebookEditInput, context: Any) -> ToolResult:
        path = Path(input.notebook_path)
        if not path.exists():
            if input.operation == "add_cell":
                return self._create_new_notebook(path, input)
            return ToolResult(output=f"文件不存在: {input.notebook_path}", is_error=True)

        if path.suffix.lower() != ".ipynb":
            return ToolResult(output="仅支持 .ipynb 文件", is_error=True)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            return ToolResult(output=f"读取 Notebook 失败: {e}", is_error=True)

        if "cells" not in data:
            data["cells"] = []

        operations = {
            "read": self._read_notebook,
            "add_cell": self._add_cell,
            "delete_cell": self._delete_cell,
            "edit_cell": self._edit_cell,
        }

        handler = operations.get(input.operation)
        if handler is None:
            return ToolResult(
                output=f"未知操作: {input.operation}。支持: {', '.join(operations.keys())}",
                is_error=True,
            )

        result = handler(data, input)
        if result.is_error:
            return result

        try:
            path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as e:
            return ToolResult(output=f"写入 Notebook 失败: {e}", is_error=True)

        return result

    def _create_new_notebook(self, path: Path, input: NotebookEditInput) -> ToolResult:
        data = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                },
                "language_info": {"name": "python", "version": "3.10.0"},
            },
            "cells": [],
        }

        cell = _make_cell(
            cell_type=input.cell_type or "code",
            source=input.source or "",
        )
        data["cells"].append(cell)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as e:
            return ToolResult(output=f"创建 Notebook 失败: {e}", is_error=True)

        return ToolResult(output=f"已创建新 Notebook: {path}（1 个单元格）")

    def _read_notebook(self, data: dict, input: NotebookEditInput) -> ToolResult:
        cells = data.get("cells", [])
        if input.cell_index is not None:
            if input.cell_index < 0 or input.cell_index >= len(cells):
                return ToolResult(
                    output=f"单元格索引越界: {input.cell_index}（共 {len(cells)} 个单元格）",
                    is_error=True,
                )
            cell = cells[input.cell_index]
            source = _get_cell_source(cell)
            output_parts = [
                f"单元格 {input.cell_index} [{cell.get('cell_type', 'code')}]:",
                source,
            ]
            if cell.get("outputs"):
                output_parts.append(f"输出: {len(cell['outputs'])} 个")
            return ToolResult(output="\n".join(output_parts))

        parts = [f"Notebook: {len(cells)} 个单元格\n"]
        for i, cell in enumerate(cells):
            source = _get_cell_source(cell)
            preview = source[:80].replace("\n", " ")
            cell_type = cell.get("cell_type", "code")
            parts.append(f"  [{i}] {cell_type}: {preview}...")
        return ToolResult(output="\n".join(parts))

    def _add_cell(self, data: dict, input: NotebookEditInput) -> ToolResult:
        cell = _make_cell(
            cell_type=input.cell_type or "code",
            source=input.source or "",
        )
        cells = data["cells"]
        if input.cell_index is not None and 0 <= input.cell_index <= len(cells):
            cells.insert(input.cell_index, cell)
            return ToolResult(output=f"已在位置 {input.cell_index} 添加 {cell['cell_type']} 单元格")
        cells.append(cell)
        return ToolResult(output=f"已添加 {cell['cell_type']} 单元格到末尾（索引 {len(cells) - 1}）")

    def _delete_cell(self, data: dict, input: NotebookEditInput) -> ToolResult:
        cells = data["cells"]
        if input.cell_index is None:
            return ToolResult(output="需要指定 cell_index", is_error=True)
        if input.cell_index < 0 or input.cell_index >= len(cells):
            return ToolResult(
                output=f"单元格索引越界: {input.cell_index}（共 {len(cells)} 个）",
                is_error=True,
            )
        removed = cells.pop(input.cell_index)
        source = _get_cell_source(removed)[:60]
        return ToolResult(
            output=f"已删除单元格 {input.cell_index}: {source}..."
        )

    def _edit_cell(self, data: dict, input: NotebookEditInput) -> ToolResult:
        cells = data["cells"]
        if input.cell_index is None:
            return ToolResult(output="需要指定 cell_index", is_error=True)
        if input.cell_index < 0 or input.cell_index >= len(cells):
            return ToolResult(
                output=f"单元格索引越界: {input.cell_index}（共 {len(cells)} 个）",
                is_error=True,
            )

        cell = cells[input.cell_index]
        if input.source is not None:
            if isinstance(cell.get("source"), list):
                cell["source"] = input.source.splitlines(True)
                if cell["source"] and not cell["source"][-1].endswith("\n"):
                    cell["source"][-1] += "\n"
            else:
                cell["source"] = input.source

        if input.cell_type is not None:
            cell["cell_type"] = input.cell_type
            if input.cell_type == "markdown":
                cell.pop("outputs", None)
                cell.pop("execution_count", None)

        source = _get_cell_source(cell)
        return ToolResult(
            output=f"已编辑单元格 {input.cell_index} [{cell.get('cell_type', 'code')}]: {source[:80]}..."
        )


def _make_cell(cell_type: str, source: str) -> dict:
    cell: dict[str, Any] = {
        "cell_type": cell_type,
        "id": uuid.uuid4().hex[:8],
        "metadata": {},
        "source": source.splitlines(True) if source else [],
    }
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def _get_cell_source(cell: dict) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return str(source)
