from __future__ import annotations

from src.skills.types import SkillDefinition


def create_debug_skill() -> SkillDefinition:
    return SkillDefinition(
        name="debug",
        description="调试 Skill：系统化地分析和修复代码问题",
        when_to_use="当代码出现错误、异常或意外行为需要调试时",
        allowed_tools=[],
        get_prompt_for_command="""你是一个专业的代码调试助手。你的任务是系统化地分析和修复代码问题。

### 调试流程
1. **复现问题**：理解错误信息和上下文
2. **定位根因**：通过搜索和阅读代码找到问题根源
3. **制定修复方案**：提出修复方案并解释原因
4. **实施修复**：修改代码解决问题
5. **验证修复**：运行相关测试或命令确认问题已解决

### 调试技巧
- 从错误堆栈入手，逐层追踪
- 检查最近的代码变更
- 使用日志和打印语句辅助定位
- 考虑边界条件和并发问题""",
        aliases=["troubleshoot"],
    )
