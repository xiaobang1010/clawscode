from __future__ import annotations

from src.skills.types import SkillDefinition


def create_verify_skill() -> SkillDefinition:
    return SkillDefinition(
        name="verify",
        description="验证 Skill：验证代码变更的正确性和完整性",
        when_to_use="当需要验证代码修改是否正确、测试是否通过、功能是否正常时",
        allowed_tools=["FileRead", "Glob", "Grep", "Bash"],
        get_prompt_for_command="""你是一个代码验证助手。你的任务是全面验证代码变更的正确性。

### 验证流程
1. **语法检查**：确保代码没有语法错误
2. **类型检查**：运行类型检查工具（如果可用）
3. **单元测试**：运行相关的单元测试
4. **集成测试**：验证与其他模块的集成
5. **边界检查**：测试边界条件和异常情况
6. **代码审查**：检查代码质量和最佳实践

### 验证报告
- 通过的检查项
- 失败的检查项及原因
- 需要人工确认的可疑点
- 总体评估和建议""",
        aliases=["check", "validate"],
    )
