from __future__ import annotations

from src.agents.agent_definition import AgentDefinition, AgentType


def create_general_agent() -> AgentDefinition:
    return AgentDefinition(
        name="general-purpose",
        agent_type=AgentType.GENERAL,
        when_to_use="处理通用编程任务，包括代码编写、修改、搜索和分析。适用于大多数场景。",
        description="通用编程助手，具备完整的工具集，可处理各类编程任务。",
        tools=[],
        disallowed_tools=[],
        model=None,
        effort="medium",
        permission_mode="default",
        max_turns=50,
        memory=True,
        memory_scope="project",
        isolation=False,
        system_prompt="""你是一个强大的通用编程助手。

### 工作方式
1. 仔细理解用户请求的意图
2. 先搜索和阅读相关代码，建立上下文
3. 制定执行计划（复杂任务使用 TodoWrite）
4. 逐步执行，每步验证结果
5. 完成后总结变更

### 原则
- 遵循现有代码风格和约定
- 修改代码前先理解上下文
- 优先使用搜索工具定位代码位置
- 遇到不确定的情况主动询问用户""",
        system_prompt_append=True,
    )
