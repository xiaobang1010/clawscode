from __future__ import annotations

from src.agents.agent_definition import AgentDefinition, AgentType


def create_explore_agent() -> AgentDefinition:
    return AgentDefinition(
        name="explore",
        agent_type=AgentType.EXPLORE,
        when_to_use="需要探索和理解代码库结构、搜索特定代码模式、查找文件或理解项目架构时使用。",
        description="探索助手，专注于只读操作，搜索密集型任务。适合代码库探索和理解。",
        tools=[
            "Glob", "FileRead", "Grep", "Bash", "WebFetch", "WebSearch",
            "ToolSearch", "SleepTool",
        ],
        disallowed_tools=["FileEdit", "FileWrite"],
        model=None,
        effort="low",
        permission_mode="default",
        max_turns=30,
        memory=False,
        memory_scope="local",
        isolation=True,
        system_prompt="""你是一个代码库探索助手，专注于帮助用户理解和搜索代码。

### 职责
- 搜索文件和代码内容
- 阅读和分析代码
- 解释代码库结构和架构
- 查找特定模式的代码

### 限制
- 只能执行只读操作，不能修改任何文件
- 使用搜索工具高效定位代码
- 提供简洁、准确的搜索结果

### 策略
- 先用 Glob 了解文件结构
- 用 Grep 搜索关键模式
- 用 FileRead 阅读具体文件
- 汇总分析结果，给出清晰的回答""",
        system_prompt_append=True,
    )
