from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Awaitable

from src.utils.git import is_git_repo, undo_checkpoint, undo_all_checkpoints, get_diff, get_checkpoint_log


class CommandRegistry:
    def __init__(self) -> None:
        self.commands: dict[str, Callable[..., Awaitable[str | None]]] = {}

    def register(self, name: str, handler: Callable[..., Awaitable[str | None]]) -> None:
        self.commands[name] = handler

    def is_command(self, text: str) -> bool:
        return text.startswith("/")

    async def execute(self, text: str, context: Any) -> str | None:
        parts = text[1:].split(maxsplit=1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        handler = self.commands.get(cmd)
        if handler:
            return await handler(args, context)
        return f"未知命令: /{cmd}"


def register_commands(registry: CommandRegistry) -> None:
    async def help_command(args: str, context: Any) -> str:
        lines = ["可用命令："]
        for name in sorted(registry.commands):
            lines.append(f"  /{name}")
        return "\n".join(lines)

    async def clear_command(args: str, context: Any) -> str | None:
        if hasattr(context, "messages"):
            context.messages.clear()
        return "对话历史已清除"

    async def config_command(args: str, context: Any) -> str:
        if hasattr(context, "settings"):
            s = context.settings
            return f"当前配置：\n  model: {s.model}\n  base_url: {s.base_url}\n  max_tokens: {s.max_tokens}"
        return "无配置信息"

    async def compact_command(args: str, context: Any) -> str:
        from src.services.token_counter import count_tokens
        from src.compact import compact_if_needed

        if not hasattr(context, "messages"):
            return "无对话历史"

        before_count = len(context.messages)
        before_tokens = count_tokens(context.messages)
        context.messages = await compact_if_needed(
            context.messages, context.settings.max_tokens
        )
        after_count = len(context.messages)
        after_tokens = count_tokens(context.messages)

        if before_count == after_count:
            return f"无需压缩（{before_count} 条消息，{before_tokens} tokens）"

        freed = before_tokens - after_tokens
        return (
            f"压缩完成：{before_count} → {after_count} 条消息，"
            f"释放 {freed} tokens"
        )

    async def model_command(args: str, context: Any) -> str:
        if args and hasattr(context, "settings"):
            context.settings.model = args
            return f"模型已切换为: {args}"
        if hasattr(context, "settings"):
            return f"当前模型: {context.settings.model}"
        return "无模型信息"

    async def mcp_command(args: str, context: Any) -> str:
        client = getattr(context, "_mcp_client", None)

        if args.strip() == "list":
            if client is None:
                return "MCP 未初始化"
            tools = client._available_tools
            if not tools:
                return "无可用 MCP 工具"
            lines = ["MCP 工具列表："]
            for t in tools:
                lines.append(f"  [{t['server']}] {t['name']}: {t['description']}")
            return "\n".join(lines)

        if client is None:
            return "MCP 未初始化"

        status = client.get_status()
        lines = ["MCP 服务器状态："]
        for name, st in status.items():
            lines.append(f"  {name}: {st}")
        return "\n".join(lines)

    async def undo_command(args: str, context: Any) -> str:
        count = getattr(context, "checkpoint_count", 0)
        if count <= 0:
            return "没有可撤销的 AI 修改"
        cwd = getattr(context, "cwd", None)
        if cwd is None:
            return "无法获取工作目录"
        if undo_checkpoint(cwd):
            context.checkpoint_count = count - 1
            return f"✅ 已撤销最近一次修改 (剩余 {context.checkpoint_count} 个 checkpoint)"
        return "撤销失败"

    async def undo_all_command(args: str, context: Any) -> str:
        count = getattr(context, "checkpoint_count", 0)
        if count <= 0:
            return "没有可撤销的 AI 修改"
        answer = input(f"确认撤销全部 {count} 次 AI 修改？(y/n): ").strip().lower()
        if answer != "y":
            return "已取消"
        cwd = getattr(context, "cwd", None)
        if cwd is None:
            return "无法获取工作目录"
        if undo_all_checkpoints(cwd, count):
            context.checkpoint_count = 0
            return f"✅ 已撤销全部 AI 修改 (共 {count} 次)"
        return "撤销失败"

    async def diff_command(args: str, context: Any) -> str:
        cwd = getattr(context, "cwd", None)
        if cwd is None or not is_git_repo(cwd):
            return "当前目录不是 git 仓库"
        diff = get_diff(cwd)
        if diff is None:
            return "没有检测到文件改动"
        return diff

    async def log_command(args: str, context: Any) -> str:
        count = getattr(context, "checkpoint_count", 0)
        if count <= 0:
            return "本次会话没有 AI 修改记录"
        cwd = getattr(context, "cwd", None)
        if cwd is None:
            return "无法获取工作目录"
        entries = get_checkpoint_log(cwd, count)
        if not entries:
            return "本次会话没有 AI 修改记录"
        lines = ["AI 修改记录："]
        for i, entry in enumerate(entries, 1):
            lines.append(f"  #{i} {entry['hash']} {entry['message']}")
        return "\n".join(lines)

    # --- 阶段十五新增命令 ---

    async def resume_command(args: str, context: Any) -> str:
        from src.services.session_restore import SessionRestore

        cwd = getattr(context, "cwd", None)
        restorer = SessionRestore(home=cwd if cwd else None)

        if args.strip():
            session_id = args.strip()
            restored = restorer.restore(session_id)
            if restored is None:
                return f"未找到会话: {session_id}"
        else:
            restored = restorer.restore_latest()
            if restored is None:
                return "没有可恢复的历史会话"

        if hasattr(context, "messages"):
            context.messages.clear()
            context.messages.extend(restored.messages)
        if hasattr(context, "session_id"):
            context.session_id = restored.metadata.get("session_id", "")
        if hasattr(context, "session_title"):
            context.session_title = restored.metadata.get("title", "")

        msg_count = restored.metadata.get("message_count", len(restored.messages))
        title = restored.metadata.get("title", "无标题")
        return f"✅ 已恢复会话: {title} ({msg_count} 条消息)"

    async def cost_command(args: str, context: Any) -> str:
        from src.services.cost_tracker import CostTrackerService

        settings = getattr(context, "settings", None)
        model = settings.model if settings else "default"
        tracker = CostTrackerService(model=model)

        if args.strip() == "history":
            summary = tracker.get_historical_summary()
            return f"📊 历史费用统计：\n{summary.format()}"

        return f"📊 当前会话费用：\n{tracker.format_session_summary()}"

    async def permissions_command(args: str, context: Any) -> str:
        from src.services.permission_persistence import PermissionPersistence

        cwd = getattr(context, "cwd", Path.cwd())
        home = Path.home()
        persistence = PermissionPersistence(cwd=Path(cwd), home=home)

        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0] if parts else ""
        subcmd_args = parts[1] if len(parts) > 1 else ""

        if subcmd == "add":
            rule_parts = subcmd_args.split(maxsplit=1)
            if len(rule_parts) < 2:
                return "用法: /permissions add <allow|deny|ask> <规则>\n示例: /permissions add allow FileRead:*"
            action, rule = rule_parts[0], rule_parts[1]
            scope = "project"
            if action == "allow":
                persistence.save_allow_rule(rule, scope)
                return f"✅ 已添加 allow 规则: {rule}"
            elif action == "deny":
                persistence.save_deny_rule(rule, scope)
                return f"✅ 已添加 deny 规则: {rule}"
            elif action == "ask":
                persistence.save_ask_rule(rule, scope)
                return f"✅ 已添加 ask 规则: {rule}"
            return f"无效操作: {action}，请使用 allow/deny/ask"

        if subcmd == "remove":
            rule_parts = subcmd_args.split(maxsplit=1)
            if len(rule_parts) < 2:
                return "用法: /permissions remove <allow|deny|ask> <规则>\n示例: /permissions remove allow FileRead:*"
            action, rule = rule_parts[0], rule_parts[1]
            if action == "allow":
                if persistence.remove_allow_rule(rule):
                    return f"✅ 已移除 allow 规则: {rule}"
                return f"未找到规则: {rule}"
            elif action == "deny":
                if persistence.remove_deny_rule(rule):
                    return f"✅ 已移除 deny 规则: {rule}"
                return f"未找到规则: {rule}"
            elif action == "ask":
                if persistence.remove_ask_rule(rule):
                    return f"✅ 已移除 ask 规则: {rule}"
                return f"未找到规则: {rule}"
            return f"无效操作: {action}，请使用 allow/deny/ask"

        if subcmd == "mode":
            mode = subcmd_args.strip().lower()
            if not mode:
                checker = getattr(context, "permission_checker", None)
                if checker:
                    return f"当前权限模式: {checker.mode.value}"
                settings = getattr(context, "settings", None)
                if settings:
                    return f"当前权限模式: {settings.permission_mode}"
                return "当前权限模式: default"

            valid_modes = {"default", "plan", "bypass", "auto"}
            if mode not in valid_modes:
                return f"无效模式: {mode}，有效值: {', '.join(sorted(valid_modes))}"

            checker = getattr(context, "permission_checker", None)
            if checker:
                from src.permissions import PermissionMode
                mode_map = {
                    "default": PermissionMode.DEFAULT,
                    "plan": PermissionMode.PLAN,
                    "bypass": PermissionMode.BYPASS,
                    "auto": PermissionMode.AUTO,
                }
                checker.set_mode(mode_map[mode])

            settings = getattr(context, "settings", None)
            if settings:
                settings.permission_mode = mode

            return f"✅ 权限模式已切换为: {mode}"

        rules = persistence.load_rules()
        lines = ["📋 权限规则："]
        lines.append(f"  Deny ({len(rules.get('deny', []))}):")
        for r in rules.get("deny", []):
            lines.append(f"    - {r}")
        lines.append(f"  Ask ({len(rules.get('ask', []))}):")
        for r in rules.get("ask", []):
            lines.append(f"    - {r}")
        lines.append(f"  Allow ({len(rules.get('allow', []))}):")
        for r in rules.get("allow", []):
            lines.append(f"    - {r}")

        checker = getattr(context, "permission_checker", None)
        if checker:
            lines.append(f"\n  当前模式: {checker.mode.value}")
        settings = getattr(context, "settings", None)
        if settings and not checker:
            lines.append(f"\n  当前模式: {settings.permission_mode}")

        return "\n".join(lines)

    async def agents_command(args: str, context: Any) -> str:
        from src.agents.loader import AgentLoader

        loader = AgentLoader()
        agents = loader.get_all()

        if not agents:
            agents = loader.load_all()

        if not agents:
            return "当前无可用 Agent"

        query = args.strip().lower()
        if query:
            matched = {
                name: defn for name, defn in agents.items()
                if query in name.lower()
                or query in defn.description.lower()
                or query in defn.when_to_use.lower()
            }
            if not matched:
                return f"未找到匹配 '{args.strip()}' 的 Agent"
            agents = matched

        lines = [f"🤖 可用 Agent ({len(agents)})："]
        for name, defn in sorted(agents.items()):
            desc = defn.description or defn.when_to_use or "无描述"
            lines.append(f"  • {name}: {desc}")
            if defn.model:
                lines.append(f"    模型: {defn.model}")
            if defn.tools:
                lines.append(f"    工具: {', '.join(defn.tools[:5])}{'...' if len(defn.tools) > 5 else ''}")

        return "\n".join(lines)

    async def skills_command(args: str, context: Any) -> str:
        from src.skills.registry import SkillRegistry

        reg = SkillRegistry()
        skills = reg.list_skills()

        if not skills:
            return "当前无可用 Skill"

        query = args.strip().lower()
        if query:
            matched = [
                s for s in skills
                if query in s.get("name", "").lower()
                or query in s.get("description", "").lower()
            ]
            if not matched:
                return f"未找到匹配 '{args.strip()}' 的 Skill"
            skills = matched

        lines = [f"⚡ 可用 Skill ({len(skills)})："]
        for skill in skills:
            name = skill.get("name", "")
            desc = skill.get("description", "")
            aliases = skill.get("aliases", [])
            alias_str = f" (别名: {', '.join(aliases)})" if aliases else ""
            lines.append(f"  • {name}{alias_str}: {desc}")

        return "\n".join(lines)

    async def plugins_command(args: str, context: Any) -> str:
        from src.plugins.registry import PluginRegistry

        reg = PluginRegistry()
        plugins = reg.list_plugins()

        if not plugins:
            return "当前无已加载插件"

        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0] if parts else ""
        subcmd_args = parts[1] if len(parts) > 1 else ""

        if subcmd == "enable":
            if not subcmd_args:
                return "用法: /plugins enable <插件名>"
            if reg.enable(subcmd_args):
                return f"✅ 已启用插件: {subcmd_args}"
            return f"启用失败: 未找到插件 '{subcmd_args}' 或插件处于错误状态"

        if subcmd == "disable":
            if not subcmd_args:
                return "用法: /plugins disable <插件名>"
            if reg.disable(subcmd_args):
                return f"✅ 已禁用插件: {subcmd_args}"
            return f"禁用失败: 未找到插件 '{subcmd_args}'"

        lines = [f"🔌 已加载插件 ({len(plugins)})："]
        for p in plugins:
            name = p.get("name", "")
            version = p.get("version", "")
            state = p.get("state", "")
            desc = p.get("description", "")
            lines.append(f"  • {name} v{version} [{state}]: {desc}")

        return "\n".join(lines)

    async def hooks_command(args: str, context: Any) -> str:
        from src.hooks.registry import HookRegistry
        from src.hooks.types import HookEvent

        reg = HookRegistry()
        hooks = reg.list_all()

        if not hooks:
            return "当前无已配置 Hooks"

        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0] if parts else ""
        subcmd_args = parts[1] if len(parts) > 1 else ""

        if subcmd == "enable":
            if not subcmd_args:
                return "用法: /hooks enable <hook名>"
            reg.enable(subcmd_args)
            return f"✅ 已启用 Hook: {subcmd_args}"

        if subcmd == "disable":
            if not subcmd_args:
                return "用法: /hooks disable <hook名>"
            reg.disable(subcmd_args)
            return f"✅ 已禁用 Hook: {subcmd_args}"

        lines = [f"🪝 已配置 Hooks ({len(hooks)})："]
        for h in hooks:
            status = "✅" if h.enabled else "❌"
            lines.append(
                f"  {status} {h.name} [{h.event.value}] ({h.hook_type.value})"
            )
            if h.command:
                lines.append(f"    命令: {h.command}")
            if h.url:
                lines.append(f"    URL: {h.url}")

        return "\n".join(lines)

    async def memory_command(args: str, context: Any) -> str:
        from src.services.memory import MemoryDiscovery

        cwd = getattr(context, "cwd", Path.cwd())
        discovery = MemoryDiscovery(cwd=Path(cwd))

        memories = discovery.discover_all()

        if not memories:
            return "当前无记忆文件 (MEMORY.md)"

        if args.strip().lower() == "show":
            content = discovery.load_merged()
            if not content.strip():
                return "记忆文件为空"
            return f"📝 记忆内容：\n{content}"

        lines = [f"📝 记忆文件 ({len(memories)})："]
        for path, level in memories:
            lines.append(f"  • [{level}] {path}")

        lines.append("\n使用 /memory show 查看详细内容")
        return "\n".join(lines)

    async def sessions_command(args: str, context: Any) -> str:
        from src.services.session_restore import SessionRestore

        cwd = getattr(context, "cwd", None)
        restorer = SessionRestore(home=cwd if cwd else None)

        parts = args.strip().split(maxsplit=1)
        subcmd = parts[0] if parts else ""
        subcmd_args = parts[1] if len(parts) > 1 else ""

        if subcmd == "delete":
            if not subcmd_args:
                return "用法: /sessions delete <session_id>"
            from src.services.session_storage import SessionStorage
            storage = SessionStorage(home=cwd if cwd else None)
            if storage.delete(subcmd_args):
                return f"✅ 已删除会话: {subcmd_args}"
            return f"未找到会话: {subcmd_args}"

        limit = 10
        if subcmd.isdigit():
            limit = int(subcmd)

        sessions = restorer.list_recent(limit=limit)
        if not sessions:
            return "没有历史会话"

        lines = [f"📂 历史会话 (最近 {len(sessions)} 个)："]
        for s in sessions:
            title = s.title or "无标题"
            sid = s.session_id[:8] if s.session_id else "?"
            updated = s.updated_at or "未知时间"
            msg_count = len(s.messages) if s.messages else 0
            lines.append(f"  • [{sid}] {title} ({msg_count} 条消息) - {updated}")

        lines.append("\n使用 /resume <session_id> 恢复会话")
        return "\n".join(lines)

    async def export_command(args: str, context: Any) -> str:
        from src.services.session_storage import SessionStorage

        parts = args.strip().split(maxsplit=1)
        fmt = parts[0] if parts else "json"
        output_path = parts[1] if len(parts) > 1 else ""

        cwd = getattr(context, "cwd", None)
        storage = SessionStorage(home=cwd if cwd else None)

        session_id = getattr(context, "session_id", "")
        if not session_id:
            return "当前无活跃会话"

        session_data = storage.load(session_id)
        if session_data is None:
            return f"未找到会话: {session_id}"

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = "md" if fmt == "markdown" else "json"
            output_path = str(Path.cwd() / f"session_{session_id[:8]}_{timestamp}.{ext}")

        if fmt == "markdown":
            lines = [f"# 会话导出: {session_data.title or '无标题'}"]
            lines.append(f"会话ID: {session_data.session_id}")
            lines.append(f"创建时间: {session_data.created_at}")
            lines.append(f"更新时间: {session_data.updated_at}")
            lines.append("")
            for msg in session_data.messages or []:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, list):
                    content_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            content_parts.append(block.get("text", ""))
                        else:
                            content_parts.append(str(block))
                    content = "\n".join(content_parts)
                lines.append(f"## {role}")
                lines.append(content)
                lines.append("")
            output = "\n".join(lines)
            Path(output_path).write_text(output, encoding="utf-8")
        else:
            data = session_data.to_dict()
            Path(output_path).write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return f"✅ 会话已导出到: {output_path}"

    async def import_command(args: str, context: Any) -> str:
        if not args.strip():
            return "用法: /import <文件路径>"

        file_path = Path(args.strip())
        if not file_path.exists():
            return f"文件不存在: {file_path}"

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"读取文件失败: {e}"

        from src.services.session_storage import SessionStorage, SessionData

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return "文件格式错误: 不是有效的 JSON"

        session_data = SessionData.from_dict(data)

        cwd = getattr(context, "cwd", None)
        storage = SessionStorage(home=cwd if cwd else None)
        storage.save(session_data)

        title = session_data.title or "无标题"
        msg_count = len(session_data.messages or [])
        return f"✅ 已导入会话: {title} ({msg_count} 条消息, ID: {session_data.session_id[:8]})"

    # --- 注册所有命令 ---

    registry.register("help", help_command)
    registry.register("clear", clear_command)
    registry.register("config", config_command)
    registry.register("compact", compact_command)
    registry.register("model", model_command)
    registry.register("mcp", mcp_command)
    registry.register("undo", undo_command)
    registry.register("undo-all", undo_all_command)
    registry.register("diff", diff_command)
    registry.register("log", log_command)
    registry.register("resume", resume_command)
    registry.register("cost", cost_command)
    registry.register("permissions", permissions_command)
    registry.register("agents", agents_command)
    registry.register("skills", skills_command)
    registry.register("plugins", plugins_command)
    registry.register("hooks", hooks_command)
    registry.register("memory", memory_command)
    registry.register("sessions", sessions_command)
    registry.register("export", export_command)
    registry.register("import", import_command)
