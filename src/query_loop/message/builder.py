from __future__ import annotations


def build_tool_calls_content(tool_calls: dict[int, dict]) -> list[dict]:
    # 将 tool_calls dict 转为 OpenAI 格式的 list
    content = []
    for idx in sorted(tool_calls):
        tc = tool_calls[idx]
        content.append(
            {
                "type": "function",
                "id": tc["id"],
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            }
        )
    return content


def collect_text_from_messages(tool_calls: dict[int, dict]) -> str:
    # 当前返回空字符串，后续可能扩展
    return ""
