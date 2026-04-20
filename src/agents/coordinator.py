from __future__ import annotations

import asyncio
import json
from typing import Any

from src.agents.agent_definition import AgentDefinition, AgentType
from src.agents.builder import AgentBuilder
from src.agents.builtins import get_builtin_agents
from src.api_client import create_stream
from src.services.prompt_builder import COORDINATOR_SYSTEM_TEMPLATE
from src.tool import Tool, ToolResult


COORDINATOR_PROMPT = """你是一个协调者 Agent，负责管理多个子 Agent 的协作。

### 职责
1. 分析用户请求，拆分为独立的子任务
2. 为每个子任务分配合适的子 Agent
3. 通过 Agent 工具调度子 Agent 执行
4. 汇总各 Agent 的结果
5. 向用户报告最终结果

### 规则
- 确保子任务之间没有冲突
- 合理分配工作量
- 处理 Agent 之间的依赖关系
- 如果一个子任务依赖另一个的结果，按顺序执行
- 独立的子任务可以并行执行

### 可用 Agent 类型
{agent_list}

### 工作流程
1. 接收用户请求
2. 分析并拆分任务
3. 选择合适的 Agent 类型
4. 调度 Agent 执行（使用 Agent 工具）
5. 汇总结果
6. 向用户报告"""


class Coordinator:
    def __init__(
        self,
        tools: list[Tool],
        model: str = "ZhipuAI/GLM-5",
        api_key: str = "",
        base_url: str = "https://api-inference.modelscope.cn/v1",
        max_turns: int = 30,
    ):
        self._tools = tools
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._max_turns = max_turns
        self._results: dict[str, str] = {}

    def _build_system_prompt(self) -> str:
        agent_list = []
        for agent in get_builtin_agents():
            agent_list.append(f"- **{agent.name}**: {agent.description}")
        return COORDINATOR_PROMPT.format(agent_list="\n".join(agent_list))

    async def run(self, user_request: str) -> str:
        messages: list[dict] = [
            {"role": "user", "content": user_request}
        ]
        system_prompt = self._build_system_prompt()

        collected_text = ""

        for _ in range(self._max_turns):
            tool_schemas = [t.get_openai_tool_schema() for t in self._tools]
            tool_map = {t.name: t for t in self._tools}

            has_tool_calls = False
            current_tool_calls: dict[int, dict] = {}
            text_parts: list[str] = []

            async for event in create_stream(
                messages,
                tool_schemas,
                system_prompt,
                model=self._model,
                api_key=self._api_key,
                base_url=self._base_url,
            ):
                if event.type == "text_delta":
                    text_parts.append(event.data.get("text", ""))
                elif event.type == "tool_calls":
                    has_tool_calls = True
                    idx = event.data.get("index", 0)
                    if idx not in current_tool_calls:
                        current_tool_calls[idx] = {
                            "id": event.data["id"],
                            "name": event.data["name"],
                            "arguments": "",
                        }
                    current_tool_calls[idx]["arguments"] += event.data.get("arguments") or ""

            collected_text += "".join(text_parts)

            if not has_tool_calls:
                break

            assistant_content = []
            for idx in sorted(current_tool_calls):
                tc = current_tool_calls[idx]
                assistant_content.append({
                    "type": "function",
                    "id": tc["id"],
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                })

            sorted_tcs = [current_tool_calls[idx] for idx in sorted(current_tool_calls)]

            async def _exec(tc: dict) -> tuple[dict, ToolResult]:
                tool = tool_map.get(tc["name"])
                if not tool:
                    return tc, ToolResult(output=f"未知工具: {tc['name']}", is_error=True)
                try:
                    tool_input = tool.input_schema(**json.loads(tc["arguments"]))
                    result = await tool.call(tool_input, None)
                except Exception as e:
                    result = ToolResult(output=f"工具执行错误: {e}", is_error=True)
                return tc, result

            results = await asyncio.gather(*[_exec(tc) for tc in sorted_tcs])

            messages.append(
                {"role": "assistant", "content": None, "tool_calls": assistant_content}
            )
            for tc, result in results:
                messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": result.output}
                )
                if tc["name"] == "Agent":
                    self._results[tc["id"]] = result.output

        return collected_text

    def get_sub_agent_results(self) -> dict[str, str]:
        return dict(self._results)
