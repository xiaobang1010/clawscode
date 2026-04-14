from __future__ import annotations

from src.agents.agent_definition import AgentDefinition, AgentType


def create_plan_agent() -> AgentDefinition:
    return AgentDefinition(
        name="plan",
        agent_type=AgentType.PLAN,
        when_to_use="需要制定执行计划、分析任务复杂度、设计实现方案时使用。专注于思考和规划，不执行实际修改。",
        description="规划助手，专注于只读操作和思考密集型任务。制定计划但不执行修改。",
        tools=[
            "Glob", "FileRead", "Grep", "Bash", "WebFetch", "WebSearch",
            "ToolSearch", "TodoWrite", "SleepTool",
        ],
        disallowed_tools=["FileEdit", "FileWrite"],
        model=None,
        effort="high",
        permission_mode="plan",
        max_turns=20,
        memory=False,
        memory_scope="local",
        isolation=True,
        system_prompt="""你是一个规划助手，专注于分析任务和制定执行计划。

### 职责
- 分析用户请求，理解需求
- 评估任务复杂度
- 搜索相关代码建立上下文
- 制定详细的执行计划
- 使用 TodoWrite 创建任务列表

### 限制
- 只能执行只读操作
- 专注于分析和规划
- 不执行实际的代码修改

### 输出格式
1. **需求分析**：理解用户的核心需求
2. **现状调研**：相关代码和架构分析
3. **实现计划**：分步骤的执行方案
4. **风险评估**：潜在问题和注意事项""",
        system_prompt_append=True,
    )
