from __future__ import annotations

from enum import IntEnum
from pathlib import Path
from typing import Any

from src.tool import Tool


class PromptPriority(IntEnum):
    DEFAULT = 0
    CUSTOM = 10
    AGENT = 20
    COORDINATOR = 30
    OVERRIDE = 40


DEFAULT_SYSTEM_TEMPLATE = """你是一个强大的 AI 编程助手，运行在 ClawsCode 环境中。

## 核心能力
- 阅读和分析代码库
- 编写和修改代码
- 执行命令和脚本
- 搜索文件和内容
- 管理项目任务

## 工作原则
- 优先使用现有代码库中的模式和约定
- 遵循安全最佳实践，不暴露或记录密钥
- 在修改代码前先理解上下文
- 使用工具完成任务，不要虚构信息

{environment_info}
{tools_section}
{custom_instructions}"""

AGENT_SYSTEM_TEMPLATE = """{base_prompt}

## Agent 配置
- Agent 名称：{agent_name}
- Agent 类型：{agent_type}
- 使用场景：{when_to_use}
- 可用工具：{allowed_tools}
- 禁用工具：{disallowed_tools}"""

COORDINATOR_SYSTEM_TEMPLATE = """{base_prompt}

## Coordinator 模式
你是一个协调者 Agent，负责管理多个子 Agent 的协作。

### 职责
1. 分析用户请求，将复杂任务拆分为可独立执行的子任务
2. 为每个子任务分配合适的 Agent 类型
3. 监控 Agent 执行进度，处理异常和失败
4. 汇总各 Agent 的结果，形成统一回复
5. 向用户报告最终结果和关键发现

### 任务拆分原则
- 子任务之间应尽量独立，减少依赖
- 每个子任务应有明确的输入和预期输出
- 避免将过大的任务分配给单个 Agent（合理控制粒度）
- 考虑哪些子任务可以并行执行

### Agent 调度原则
- 根据任务性质选择合适的 Agent 类型
- 尽可能并行启动多个 Agent 以提高效率
- 在单个消息中发起多个 Agent 调用（使用多个工具使用块）
- 不要等待一个 Agent 完成后再启动另一个独立的 Agent

### 结果汇总原则
- 综合 Agent 返回的结果，不要遗漏关键信息
- 识别 Agent 结果之间的冲突或矛盾，进行仲裁
- 用清晰的结构向用户呈现汇总结果
- 如果某个 Agent 失败，说明失败原因并提出替代方案

### 规则
- 确保子任务之间没有资源冲突（如同时编辑同一文件）
- 不要在 Agent 运行期间主动检查其进度
- 不要捏造或预测 Agent 的结果"""


class PromptBuilder:
    def __init__(self, cwd: Path, tools: list[Tool] | None = None):
        self._cwd = cwd
        self._tools = tools or []
        self._layers: dict[PromptPriority, str] = {}
        self._agent_config: dict[str, Any] | None = None
        self._is_coordinator = False
        self._custom_instructions = ""
        self._skills_section = ""

    def set_custom_instructions(self, instructions: str) -> PromptBuilder:
        self._custom_instructions = instructions
        if instructions:
            self._layers[PromptPriority.CUSTOM] = instructions
        return self

    def set_agent_config(
        self,
        name: str,
        agent_type: str,
        when_to_use: str = "",
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
    ) -> PromptBuilder:
        self._agent_config = {
            "name": name,
            "type": agent_type,
            "when_to_use": when_to_use,
            "allowed_tools": allowed_tools or [],
            "disallowed_tools": disallowed_tools or [],
        }
        return self

    def set_coordinator_mode(self, enabled: bool = True) -> PromptBuilder:
        self._is_coordinator = enabled
        return self

    def set_override(self, prompt: str) -> PromptBuilder:
        if prompt:
            self._layers[PromptPriority.OVERRIDE] = prompt
        return self

    def set_skills_section(self, skills_section: str) -> PromptBuilder:
        self._skills_section = skills_section
        return self

    def build(self, environment_info: str = "") -> str:
        if PromptPriority.OVERRIDE in self._layers:
            return self._layers[PromptPriority.OVERRIDE]

        base_prompt = self._build_base(environment_info)

        if self._is_coordinator:
            base_prompt = self._build_coordinator(base_prompt)
        elif self._agent_config:
            base_prompt = self._build_agent(base_prompt)

        return base_prompt

    def _build_base(self, environment_info: str) -> str:
        tools_section = self._build_tools_section()
        custom = self._layers.get(PromptPriority.CUSTOM, self._custom_instructions)
        skills = self._skills_section

        if tools_section:
            tools_section = f"\n{tools_section}\n"

        return DEFAULT_SYSTEM_TEMPLATE.format(
            environment_info=environment_info,
            tools_section=tools_section,
            custom_instructions=custom,
        ) + (f"\n\n{skills}" if skills else "")

    def _build_tools_section(self) -> str:
        return ""

    def _build_agent(self, base_prompt: str) -> str:
        if not self._agent_config:
            return base_prompt

        cfg = self._agent_config
        return AGENT_SYSTEM_TEMPLATE.format(
            base_prompt=base_prompt,
            agent_name=cfg["name"],
            agent_type=cfg["type"],
            when_to_use=cfg["when_to_use"],
            allowed_tools=", ".join(cfg["allowed_tools"]) or "全部",
            disallowed_tools=", ".join(cfg["disallowed_tools"]) or "无",
        )

    def _build_coordinator(self, base_prompt: str) -> str:
        return COORDINATOR_SYSTEM_TEMPLATE.format(base_prompt=base_prompt)


def build_system_prompt(
    cwd: Path,
    tools: list[Tool],
    environment_info: str = "",
    custom_instructions: str = "",
    agent_config: dict[str, Any] | None = None,
    is_coordinator: bool = False,
    override_prompt: str = "",
    skills_section: str = "",
) -> str:
    builder = PromptBuilder(cwd, tools)

    if custom_instructions:
        builder.set_custom_instructions(custom_instructions)
    if override_prompt:
        builder.set_override(override_prompt)
    if is_coordinator:
        builder.set_coordinator_mode()
    if agent_config:
        builder.set_agent_config(**agent_config)
    if skills_section:
        builder.set_skills_section(skills_section)

    return builder.build(environment_info=environment_info)


def build_skills_section(skills_registry_or_list: Any) -> str:
    from src.skills.types import SkillDefinition

    if hasattr(skills_registry_or_list, "get_all"):
        skills = list(skills_registry_or_list.get_all().values())
    elif isinstance(skills_registry_or_list, list):
        skills = skills_registry_or_list
    else:
        return ""

    if not skills:
        return ""

    lines = ["## 可用技能（Skills）", ""]
    lines.append("使用 Skill 工具加载技能以获得特定领域的专业指导。")
    lines.append("")

    for skill in skills:
        if not isinstance(skill, SkillDefinition):
            continue
        aliases = f" (别名: {', '.join(skill.aliases)})" if skill.aliases else ""
        lines.append(f"- **{skill.name}**{aliases}: {skill.description}")
        lines.append(f"  使用场景：{skill.when_to_use}")

    lines.append("")
    lines.append("调用方式：使用 Skill 工具，传入技能名称或别名即可加载。")

    return "\n".join(lines)
