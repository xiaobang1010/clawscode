from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from src.agents.agent_definition import AgentDefinition
from src.agents.builtins import get_builtin_agents
from src.agents.builder import AgentBuilder
from src.agents.display import AgentDisplayManager
from src.api_client import create_stream
from src.tool import Tool, ToolResult


@dataclass
class SwarmMember:
    member_id: str
    agent_name: str
    definition: AgentDefinition
    status: str = "idle"


@dataclass
class SwarmTeam:
    team_id: str
    name: str
    members: dict[str, SwarmMember] = field(default_factory=dict)
    created_at: float = 0.0
    status: str = "active"


_teams: dict[str, SwarmTeam] = {}
_display = AgentDisplayManager()


class TeamCreateInput(BaseModel):
    team_name: str = Field(description="团队名称")
    agent_types: list[str] = Field(description="团队成员的 Agent 类型列表")


class TeamDeleteInput(BaseModel):
    team_id: str = Field(description="要解散的团队 ID")


class TeamListInput(BaseModel):
    pass


class SwarmDispatchInput(BaseModel):
    team_id: str = Field(description="团队 ID")
    task: str = Field(description="要执行的任务")
    parallel: bool = Field(default=True, description="是否并行执行")


class TeamCreateTool(Tool):
    name = "TeamCreate"
    description = "创建多 Agent 团队，指定团队成员的 Agent 类型。"
    input_schema = TeamCreateInput
    is_readonly = False

    async def call(self, input: TeamCreateInput, context: Any) -> ToolResult:
        import time

        team_id = str(uuid.uuid4())[:8]
        team = SwarmTeam(
            team_id=team_id,
            name=input.team_name,
            created_at=time.time(),
        )

        available = {a.name: a for a in get_builtin_agents()}

        for agent_type in input.agent_types:
            definition = available.get(agent_type)
            if not definition:
                return ToolResult(
                    output=f"未找到 Agent 类型: {agent_type}",
                    is_error=True,
                )
            member_id = str(uuid.uuid4())[:8]
            team.members[member_id] = SwarmMember(
                member_id=member_id,
                agent_name=definition.name,
                definition=definition,
            )

        _teams[team_id] = team
        member_names = [m.agent_name for m in team.members.values()]
        return ToolResult(
            output=f"团队 '{input.team_name}' 已创建 (ID: {team_id})\n成员: {', '.join(member_names)}"
        )


class TeamDeleteTool(Tool):
    name = "TeamDelete"
    description = "解散指定的多 Agent 团队。"
    input_schema = TeamDeleteInput
    is_readonly = False

    async def call(self, input: TeamDeleteInput, context: Any) -> ToolResult:
        team = _teams.pop(input.team_id, None)
        if not team:
            return ToolResult(
                output=f"未找到团队: {input.team_id}",
                is_error=True,
            )
        return ToolResult(
            output=f"团队 '{team.name}' (ID: {input.team_id}) 已解散，共 {len(team.members)} 个成员"
        )


class TeamListTool(Tool):
    name = "TeamList"
    description = "列出所有活跃的多 Agent 团队。"
    input_schema = TeamListInput
    is_readonly = True

    async def call(self, input: TeamListInput, context: Any) -> ToolResult:
        if not _teams:
            return ToolResult(output="当前没有活跃的团队。")

        lines = []
        for team in _teams.values():
            members = ", ".join(m.agent_name for m in team.members.values())
            lines.append(f"- 团队 '{team.name}' (ID: {team.team_id}): {members}")

        return ToolResult(output="\n".join(lines))


class SwarmDispatchTool(Tool):
    name = "SwarmDispatch"
    description = "将任务分发给 Swarm 团队成员执行，支持并行或串行模式。"
    input_schema = SwarmDispatchInput
    is_readonly = False

    async def _execute_member(self, member: SwarmMember, task: str) -> str:
        from src.tools import get_tools

        all_tools = get_tools()
        builder = AgentBuilder(all_tools)
        tools = builder.build_tools(member.definition)
        system_prompt = builder.build_system_prompt(member.definition)
        tool_schemas = [t.get_openai_tool_schema() for t in tools]

        messages = [{"role": "user", "content": task}]

        collected: list[str] = []
        model = member.definition.get_model_override() or "ZhipuAI/GLM-5"
        async for event in create_stream(
            messages=messages,
            tools=tool_schemas,
            system=system_prompt,
            model=model,
        ):
            if event.type == "text_delta":
                collected.append(event.data["text"])

        return "".join(collected)

    async def call(self, input: SwarmDispatchInput, context: Any) -> ToolResult:
        team = _teams.get(input.team_id)
        if not team:
            return ToolResult(
                output=f"未找到团队: {input.team_id}",
                is_error=True,
            )

        if not team.members:
            return ToolResult(output="团队没有成员", is_error=True)

        members = list(team.members.values())

        if input.parallel:
            results = await asyncio.gather(
                *[self._execute_member(m, input.task) for m in members]
            )
        else:
            results = []
            for m in members:
                result = await self._execute_member(m, input.task)
                results.append(result)

        output_parts = []
        for member, result in zip(members, results):
            output_parts.append(f"【{member.agent_name}】\n{result}")

        return ToolResult(output="\n\n".join(output_parts))
