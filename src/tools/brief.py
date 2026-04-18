from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.tool import Tool, ToolResult


class BriefInput(BaseModel):
    content: str = Field(description="需要生成摘要的内容")
    max_length: int = Field(default=500, description="摘要最大长度（字符数）", ge=50, le=5000)
    focus: str | None = Field(default=None, description="摘要焦点（如：错误、架构、变更等）")


class BriefTool(Tool):
    name = "Brief"
    description = "生成上下文摘要。对给定内容提取关键信息，生成结构化摘要。"
    input_schema = BriefInput
    is_readonly = True

    async def call(self, input: BriefInput, context: Any) -> ToolResult:
        content = input.content
        if not content.strip():
            return ToolResult(output="无内容可摘要", is_error=True)

        summary_parts: list[str] = []

        summary_parts.append(_extract_key_topics(content))

        if input.focus:
            summary_parts.append(f"焦点: {input.focus}")
            summary_parts.append(_extract_focused_content(content, input.focus))
        else:
            summary_parts.append(_extract_structured_summary(content))

        entities = _extract_entities(content)
        if entities:
            summary_parts.append(f"关键实体: {', '.join(entities[:20])}")

        result = "\n".join(summary_parts)

        if len(result) > input.max_length:
            result = result[:input.max_length] + "\n...[摘要已截断]"

        return ToolResult(output=result)


def _extract_key_topics(content: str) -> str:
    lines = content.strip().splitlines()
    non_empty = [l.strip() for l in lines if l.strip()]
    if not non_empty:
        return "主题: (无法识别)"

    heading_keywords = ["#", "##", "###", "title:", "subject:", "topic:"]
    headings = [
        l for l in non_empty[:20]
        if any(l.lower().startswith(kw) for kw in heading_keywords)
    ]

    if headings:
        topics = [h.lstrip("# ").strip() for h in headings[:5]]
        return f"主题: {'; '.join(topics)}"

    first_lines = non_empty[:3]
    return f"主题概要: {' '.join(first_lines)[:200]}"


def _extract_focused_content(content: str, focus: str) -> str:
    focus_lower = focus.lower()
    lines = content.splitlines()
    relevant: list[str] = []
    context_window = 2

    for i, line in enumerate(lines):
        if focus_lower in line.lower():
            start = max(0, i - context_window)
            end = min(len(lines), i + context_window + 1)
            for j in range(start, end):
                if lines[j].strip() and lines[j] not in relevant:
                    relevant.append(lines[j])

    if not relevant:
        return f"未找到与 '{focus}' 相关的内容"

    return f"相关内容:\n" + "\n".join(relevant[:30])


def _extract_structured_summary(content: str) -> str:
    lines = content.strip().splitlines()
    total_lines = len(lines)
    total_chars = len(content)

    sections: list[str] = []
    current_section: list[str] = []
    section_titles: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("##"):
            if current_section:
                sections.append("\n".join(current_section))
                current_section = []
            title = stripped.lstrip("# ").strip()
            section_titles.append(title)
        current_section.append(line)
    if current_section:
        sections.append("\n".join(current_section))

    parts: list[str] = [f"总览: {total_lines} 行, {total_chars} 字符"]

    if section_titles:
        parts.append(f"章节: {'; '.join(section_titles[:10])}")

    code_blocks = content.count("```")
    if code_blocks >= 2:
        parts.append(f"代码块: {code_blocks // 2} 个")

    error_indicators = sum(
        1 for kw in ["error", "exception", "traceback", "failed", "错误", "失败"]
        if kw in content.lower()
    )
    if error_indicators:
        parts.append(f"错误相关: {error_indicators} 处")

    if sections:
        first_section_lines = sections[0].splitlines()
        preview = "\n".join(first_section_lines[:5])
        parts.append(f"开头预览:\n{preview[:300]}")

    return "\n".join(parts)


def _extract_entities(content: str) -> list[str]:
    import re

    entities: list[str] = []
    seen: set[str] = set()

    file_patterns = re.findall(r'[\w/\\.-]+\.\w{1,10}', content)
    for fp in file_patterns[:15]:
        if fp not in seen and len(fp) > 3:
            entities.append(fp)
            seen.add(fp)

    func_patterns = re.findall(r'(?:def |function |class |async def )(\w+)', content)
    for fp in func_patterns[:10]:
        if fp not in seen:
            entities.append(fp)
            seen.add(fp)

    return entities
