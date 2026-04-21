from __future__ import annotations

from src.skills.types import SkillDefinition


def create_simplify_skill() -> SkillDefinition:
    return SkillDefinition(
        name="simplify",
        description="简化 Skill：简化和重构复杂代码",
        when_to_use="当代码过于复杂、需要简化或重构以提高可读性和可维护性时",
        allowed_tools=["FileRead", "FileEdit", "FileWrite", "Glob", "Grep", "Bash"],
        get_prompt_for_command="""你是一个代码简化和重构助手。你的任务是简化复杂代码，提高可读性和可维护性。

### 简化原则
1. **减少嵌套**：使用早返回、提取方法等减少嵌套层级
2. **提取函数**：将长函数拆分为小的、单一职责的函数
3. **消除重复**：识别并消除重复代码（DRY 原则）
4. **简化条件**：使用卫语句、策略模式等简化条件逻辑
5. **改善命名**：使用清晰、一致的命名

### 安全规则
- 重构不改变外部行为
- 每次重构保持小步骤
- 确保测试通过后再继续""",
        aliases=["refactor", "clean"],
    )
