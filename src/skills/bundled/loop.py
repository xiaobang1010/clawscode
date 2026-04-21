from __future__ import annotations

from src.skills.types import SkillDefinition


def create_loop_skill() -> SkillDefinition:
    return SkillDefinition(
        name="loop",
        description="循环 Skill：迭代执行任务直到满足条件",
        when_to_use="当需要反复执行某个操作直到达到目标或条件满足时",
        allowed_tools=["FileRead", "FileEdit", "FileWrite", "Glob", "Grep", "Bash", "WebSearch"],
        get_prompt_for_command="""你是一个迭代任务执行器。你的任务是反复执行操作直到满足退出条件。

### 工作方式
1. 确定初始状态和目标条件
2. 执行一步操作
3. 检查是否满足退出条件
4. 如果未满足，调整策略并继续执行
5. 达到最大迭代次数时停止并报告进度

### 安全限制
- 最大迭代次数：20
- 每次迭代必须检查退出条件
- 避免无限循环，如果连续 3 次没有进展则停止""",
        aliases=["iterate", "repeat"],
    )
