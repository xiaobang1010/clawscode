from __future__ import annotations

from src.skills.types import SkillDefinition


def create_stuck_skill() -> SkillDefinition:
    return SkillDefinition(
        name="stuck",
        description="卡住检测 Skill：检测和恢复陷入僵局的任务",
        when_to_use="当任务似乎陷入僵局、重复相同操作或无法取得进展时",
        allowed_tools=["FileRead", "Glob", "Grep", "Bash"],
        get_prompt_for_command="""你是一个僵局检测和恢复助手。你的任务是识别任务陷入僵局的原因并帮助恢复。

### 检测信号
- 重复执行相同的操作或搜索
- 连续多次获得相同的结果
- 工具调用没有带来新的信息
- 进度停滞超过 3 轮

### 恢复策略
1. **暂停并分析**：回顾已执行的操作和结果
2. **重新评估方法**：当前方法是否正确？
3. **尝试替代方案**：换一个角度或工具
4. **缩小范围**：将大问题拆分为更小的子问题
5. **寻求帮助**：向用户说明情况并请求指导""",
        aliases=["unstick", "unstuck"],
    )
