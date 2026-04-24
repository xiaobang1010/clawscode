from __future__ import annotations

from src.skills.types import SkillDefinition


def create_dream_skill() -> SkillDefinition:
    return SkillDefinition(
        name="dream",
        description="提炼日志记忆为结构化知识",
        when_to_use="当日志记忆积累到一定量，需要提炼关键信息时使用",
        allowed_tools=["FileRead", "FileWrite", "Glob", "Grep"],
        get_prompt_for_command="""分析项目中的日志式记忆文件，提炼关键信息为结构化记忆。

步骤：
1. 读取 {memory_dir}/daily/ 目录下的所有日志文件
2. 分析日志内容，识别重复出现的主题、重要决策、关键发现
3. 将提炼结果保存为结构化记忆文件（project/reference 类型）
4. 将已提炼的日志文件移动到 archive 目录

提炼规则：
- 只保留不可从代码推导的信息
- 合并重复条目
- 标注信息来源日期
- 按主题分类整理
""",
        aliases=["refine-memories", "consolidate"],
    )
