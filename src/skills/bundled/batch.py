from __future__ import annotations

from src.skills.types import SkillDefinition


def create_batch_skill() -> SkillDefinition:
    return SkillDefinition(
        name="batch",
        description="批处理 Skill：对多个文件或目标执行相同的操作序列",
        when_to_use="当需要对多个文件执行相同的编辑、搜索或转换操作时",
        allowed_tools=["FileRead", "FileEdit", "FileWrite", "Glob", "Grep", "Bash"],
        get_prompt_for_command="""你是一个批处理执行器。你的任务是对一组目标执行相同的操作。

### 工作方式
1. 解析用户提供的操作描述
2. 确定目标列表（文件、目录等）
3. 对每个目标执行相同操作
4. 汇总执行结果，报告成功和失败的数量

### 规则
- 操作必须是幂等的（重复执行不会导致问题）
- 遇到错误时记录并继续处理下一个目标
- 完成后提供汇总报告""",
        aliases=["batch-process", "bulk"],
    )
