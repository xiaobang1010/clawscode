from __future__ import annotations

from src.agents.agent_definition import AgentDefinition, AgentType


def create_verification_agent() -> AgentDefinition:
    return AgentDefinition(
        name="verification",
        agent_type=AgentType.VERIFICATION,
        when_to_use="需要验证代码正确性、运行测试、检查构建结果、进行代码审查时使用。",
        description="验证助手，专注于运行测试、检查代码质量、验证构建结果。",
        tools=[
            "Glob", "FileRead", "Grep", "Bash", "ToolSearch", "SleepTool",
        ],
        disallowed_tools=["FileEdit", "FileWrite", "WebFetch", "WebSearch"],
        model=None,
        effort="medium",
        permission_mode="default",
        max_turns=30,
        memory=False,
        memory_scope="local",
        isolation=True,
        system_prompt="""你是一个验证助手，专注于检查代码正确性和运行测试。

### 职责
- 运行测试套件
- 检查构建/编译结果
- 代码质量审查
- 发现并报告错误

### 工作方式
1. 先了解项目结构，确定测试框架
2. 运行相关测试
3. 分析测试结果
4. 如果有失败，定位错误原因
5. 提供清晰的结果报告

### 报告格式
- 通过的测试数量
- 失败的测试及原因
- 代码质量建议
- 潜在的改进点""",
        system_prompt_append=True,
    )
