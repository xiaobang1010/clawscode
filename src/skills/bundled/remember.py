from __future__ import annotations

from src.skills.types import SkillDefinition


def create_remember_skill() -> SkillDefinition:
    return SkillDefinition(
        name="remember",
        description="记忆 Skill：保存和检索重要信息到项目记忆中",
        when_to_use="当需要记住项目约定、重要决策或常用模式时",
        allowed_tools=[],
        get_prompt_for_command="""你是一个记忆管理助手。你的任务是帮助保存和检索项目中的重要信息。

### 记忆类型
1. **项目约定**：代码风格、命名规范、架构决策
2. **重要决策**：技术选型、API 设计、数据库 schema
3. **常用模式**：常用命令、配置模板、部署步骤
4. **经验教训**：遇到的问题和解决方案

### 工作方式
- 保存信息时：提取关键信息，使用简洁清晰的描述
- 检索信息时：根据上下文找到最相关的记忆
- 更新信息时：保持记忆的最新和准确""",
        aliases=["memory", "memo"],
    )
