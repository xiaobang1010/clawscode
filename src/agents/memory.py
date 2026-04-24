from __future__ import annotations

import copy
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MemoryScope(str, Enum):
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


class MemoryType(str, Enum):
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"


@dataclass
class MemoryEntry:
    key: str
    value: str
    scope: MemoryScope
    agent_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class MemorySnapshot:
    agent_name: str
    entries: list[MemoryEntry]
    timestamp: float = field(default_factory=time.time)


MEMORY_MAX_LINES = 200
MEMORY_MAX_SIZE = 25 * 1024
MEMORY_EXPIRY_DAYS = 90


WHAT_NOT_TO_SAVE_SECTION = """## 不要保存以下类型的信息

以下信息不应保存到记忆中，因为它们可以从项目本身推导或已有权威来源：

- **代码模式/约定/架构/文件路径/项目结构** — 可通过浏览项目代码获得
- **Git 历史/最近变更** — `git log` / `git blame` 是权威来源
- **调试解决方案** — 修复在代码中，上下文在 commit message 中
- **已在 CLAWS.md 中文档化的内容** — 重复保存浪费空间
- **临时任务细节** — 进行中的工作、临时状态、当前对话上下文
- **可通过标准工具推导的信息** — 如包版本（pip list）、系统信息（uname）等
"""

MEMORY_DRIFT_CAVEAT = """<warning>
记忆可能随时间过时。在使用记忆中的信息前，请验证其与当前状态一致：
- 检查引用的文件/函数是否仍然存在
- 确认配置/依赖项是否已更改
- 核实工作流/流程是否已更新
如果记忆与当前观察冲突，请信任当前观察到的信息。
</warning>"""

TRUSTING_RECALL_SECTION = """<recall-guidance>
基于记忆推荐前，请先验证：
1. 引用的函数/方法是否存在于当前代码中
2. 提到的文件路径是否有效
3. 配置标志/环境变量是否仍然正确
4. 第三方库版本是否与记忆一致
如发现记忆过时，请更新或移除过时条目。
</recall-guidance>"""

WHEN_TO_ACCESS_SECTION = f"""## 记忆访问时机指导

{MEMORY_DRIFT_CAVEAT}

{TRUSTING_RECALL_SECTION}

### 何时读取记忆
- 会话开始时（自动加载）
- 需要了解用户偏好时
- 需要项目特定上下文时

### 何时写入记忆
- 用户明确表达了长期偏好
- 发现项目特定的非显而易见的知识
- 用户纠正了 Agent 的行为（反馈）
- 重要决策的记录（不可从代码推导）

{WHAT_NOT_TO_SAVE_SECTION}
"""

MEMORY_TYPE_GUIDES = {
    "user": {
        "when_to_save": "当识别到用户的长期偏好、角色、目标、知识水平时保存",
        "how_to_use": "在交互时参考用户偏好调整行为风格、解释深度、技术选择",
        "body_structure": "简明描述偏好，使用 bullet points，避免冗长叙述",
        "examples": [
            "用户偏好使用 TypeScript 而非 JavaScript",
            "用户是高级开发者，偏好简洁的解释",
            "用户使用 vim 作为主要编辑器",
        ],
    },
    "feedback": {
        "when_to_save": "当用户纠正 Agent 行为或明确表达喜好时保存",
        "how_to_use": "优先遵循反馈记忆，避免重复犯错",
        "body_structure": "描述错误行为和正确行为的对比",
        "examples": [
            "不要在测试文件中使用相对导入",
            "用户要求提交信息使用中文",
            "不要自动运行 npm start",
        ],
    },
    "project": {
        "when_to_save": "当识别到项目的不可推导知识（决策原因、隐藏约定）时保存",
        "how_to_use": "在项目相关操作时参考，保持与项目约定一致",
        "body_structure": "项目名称 + 具体知识条目",
        "examples": [
            "API 认证使用自定义 header X-Token 而非 Bearer",
            "数据库迁移必须在周一执行",
            "生产环境不允许使用 debug 日志",
        ],
    },
    "reference": {
        "when_to_save": "当识别到外部系统资源的指针（API 端点、文档链接）时保存",
        "how_to_use": "需要访问外部系统时查找对应引用",
        "body_structure": "资源名称 + 类型 + 访问方式",
        "examples": [
            "API 文档: https://internal.example.com/api-docs",
            "staging 环境: staging.example.com:8443",
            "监控面板: grafana.internal.local/d/project-x",
        ],
    },
}


class AgentMemory:
    def __init__(
        self,
        cwd: Path,
        home: Path | None = None,
        agent_name: str = "",
    ):
        self._cwd = cwd.resolve()
        self._home = home or Path.home()
        self._agent_name = agent_name
        self._store: dict[MemoryScope, dict[str, MemoryEntry]] = {
            MemoryScope.USER: {},
            MemoryScope.PROJECT: {},
            MemoryScope.LOCAL: {},
        }
        self._snapshots: list[MemorySnapshot] = []

    def read(self, key: str, scope: MemoryScope | None = None) -> str | None:
        if scope:
            entry = self._store[scope].get(key)
            return entry.value if entry else None

        for s in (MemoryScope.LOCAL, MemoryScope.PROJECT, MemoryScope.USER):
            entry = self._store[s].get(key)
            if entry:
                return entry.value
        return None

    def read_all(self, scope: MemoryScope | None = None) -> dict[str, str]:
        result: dict[str, str] = {}
        scopes = [scope] if scope else [MemoryScope.USER, MemoryScope.PROJECT, MemoryScope.LOCAL]
        for s in scopes:
            for key, entry in self._store[s].items():
                if key not in result:
                    result[key] = entry.value
        return result

    def write(self, key: str, value: str, scope: MemoryScope = MemoryScope.PROJECT) -> None:
        self._store[scope][key] = MemoryEntry(
            key=key,
            value=value,
            scope=scope,
            agent_name=self._agent_name,
        )

    def delete(self, key: str, scope: MemoryScope | None = None) -> bool:
        if scope:
            if key in self._store[scope]:
                del self._store[scope][key]
                return True
            return False

        for s in MemoryScope:
            if key in self._store[s]:
                del self._store[s][key]
                return True
        return False

    def take_snapshot(self) -> MemorySnapshot:
        entries: list[MemoryEntry] = []
        for scope_store in self._store.values():
            entries.extend(scope_store.values())
        snapshot = MemorySnapshot(
            agent_name=self._agent_name,
            entries=copy.deepcopy(entries),
        )
        self._snapshots.append(snapshot)
        return snapshot

    def restore_snapshot(self, snapshot: MemorySnapshot) -> None:
        for scope in self._store:
            self._store[scope].clear()
        for entry in snapshot.entries:
            self._store[entry.scope][entry.key] = copy.deepcopy(entry)

    def get_snapshots(self) -> list[MemorySnapshot]:
        return list(self._snapshots)

    def _get_memory_dir(self, scope: MemoryScope) -> Path:
        remote_dir = os.environ.get("CLAWSCODE_REMOTE_MEMORY_DIR", "")
        if remote_dir and scope == MemoryScope.PROJECT:
            return Path(remote_dir)

        if scope == MemoryScope.USER:
            return self._home / ".clawscode" / "memdir"
        elif scope == MemoryScope.PROJECT:
            return self._cwd / ".clawscode" / "memdir"
        else:
            return self._cwd / "memdir"

    def _get_team_memory_dir(self, scope: MemoryScope = MemoryScope.PROJECT) -> Path:
        base = self._get_memory_dir(scope)
        return base / "team"

    def ensure_memory_dir_exists(self) -> None:
        for scope in MemoryScope:
            d = self._get_memory_dir(scope)
            d.mkdir(parents=True, exist_ok=True)

    def write_memory_file(
        self,
        name: str,
        content: str,
        memory_type: str = "project",
        description: str = "",
        scope: MemoryScope = MemoryScope.PROJECT,
    ) -> bool:
        warnings = _check_save_exclusion(content)
        if warnings:
            logger.warning(f"记忆内容违反排除规则: {warnings}")

        memory_dir = self._get_memory_dir(scope)
        try:
            memory_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        filename = f"{safe_name}.md"
        filepath = memory_dir / filename

        if not validate_memory_path(str(filepath)):
            logger.error(f"记忆路径安全验证失败: {filepath}")
            return False

        frontmatter_lines = [
            "---",
            f"name: {name}",
            f"type: {memory_type}",
            f"description: {description or name}",
            f"agent: {self._agent_name}",
            "---",
            "",
        ]

        try:
            filepath.write_text(
                "\n".join(frontmatter_lines) + content, encoding="utf-8"
            )
            self.write(key=f"file:{name}", value=content[:500], scope=scope)
            return True
        except OSError:
            return False

    def read_memory_file(self, name: str, scope: MemoryScope = MemoryScope.PROJECT) -> str | None:
        memory_dir = self._get_memory_dir(scope)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        filepath = memory_dir / f"{safe_name}.md"

        if not validate_memory_path(str(filepath)):
            logger.error(f"记忆路径安全验证失败: {filepath}")
            return None

        if not filepath.exists():
            return None
        try:
            raw = filepath.read_text(encoding="utf-8")
            if raw.startswith("---"):
                end = raw.find("---", 3)
                if end != -1:
                    return raw[end + 3:].strip()
            return raw.strip()
        except (OSError, UnicodeDecodeError):
            return None

    def list_memory_files(self, scope: MemoryScope | None = None) -> list[dict]:
        scopes = [scope] if scope else list(MemoryScope)
        results = []
        for s in scopes:
            memory_dir = self._get_memory_dir(s)
            if not memory_dir.exists():
                continue
            for f in sorted(memory_dir.glob("*.md")):
                try:
                    raw = f.read_text(encoding="utf-8")
                    meta = {"name": f.stem, "scope": s.value, "path": str(f)}
                    if raw.startswith("---"):
                        end = raw.find("---", 3)
                        if end != -1:
                            header = raw[3:end].strip()
                            for line in header.split("\n"):
                                if ":" in line:
                                    k, v = line.split(":", 1)
                                    meta[k.strip()] = v.strip()
                    meta["size"] = len(raw)
                    meta["is_expired"] = _is_memory_expired(f)
                    results.append(meta)
                except (OSError, UnicodeDecodeError):
                    continue
        return results

    def load_from_memory_files(self) -> None:
        if os.environ.get("CLAWSCODE_DISABLE_AUTO_MEMORY"):
            logger.info("自动记忆加载已禁用 (CLAWSCODE_DISABLE_AUTO_MEMORY)")
            return

        from src.services.memory import MemoryDiscovery

        discovery = MemoryDiscovery(self._cwd, self._home)
        discovered = discovery.discover_all()

        scope_map = {
            "home": MemoryScope.USER,
            "project": MemoryScope.PROJECT,
            "local": MemoryScope.LOCAL,
        }

        for path, level in discovered:
            scope = MemoryScope.PROJECT
            for prefix, s in scope_map.items():
                if level.startswith(prefix):
                    scope = s
                    break

            try:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    self.write(
                        key=f"memory:{path}",
                        value=content,
                        scope=scope,
                    )
            except (OSError, UnicodeDecodeError):
                continue

    def save_to_file(self, content: str, scope: MemoryScope = MemoryScope.PROJECT) -> bool:
        if scope == MemoryScope.USER:
            target_dir = self._home / ".clawscode" / "memdir"
        elif scope == MemoryScope.PROJECT:
            target_dir = self._cwd / ".clawscode" / "memdir"
        else:
            target_dir = self._cwd / "memdir"

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            lines = content.split("\n")
            if len(lines) > MEMORY_MAX_LINES:
                content = "\n".join(lines[:MEMORY_MAX_LINES])
            if len(content.encode("utf-8")) > MEMORY_MAX_SIZE:
                content = content.encode("utf-8")[:MEMORY_MAX_SIZE].decode("utf-8", errors="ignore")
            target_file = target_dir / "MEMORY.md"
            target_file.write_text(content, encoding="utf-8")
            return True
        except OSError:
            return False

    def format_for_prompt(self) -> str:
        all_entries = self.read_all()
        file_entries = self.list_memory_files()

        parts = []

        parts.append(WHEN_TO_ACCESS_SECTION)

        if file_entries:
            parts.append("\n## 持久化记忆文件")
            for entry in file_entries:
                desc = entry.get("description", entry["name"])
                expired_tag = " [可能过时]" if entry.get("is_expired") else ""
                parts.append(f"- **{entry['name']}** ({entry['scope']}){expired_tag}: {desc}")

        if all_entries:
            parts.append(f"\n## Agent 记忆 ({self._agent_name})")
            for key, value in all_entries.items():
                parts.append(f"- **{key}**: {value[:200]}")

        return "\n".join(parts) if parts else ""

    def write_team_memory_file(
        self,
        name: str,
        content: str,
        memory_type: str = "project",
        description: str = "",
        scope: MemoryScope = MemoryScope.PROJECT,
    ) -> bool:
        team_dir = self._get_team_memory_dir(scope)
        try:
            team_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        filepath = team_dir / f"{safe_name}.md"

        if not validate_memory_path(str(filepath)):
            logger.error(f"记忆路径安全验证失败: {filepath}")
            return False

        frontmatter_lines = [
            "---",
            f"name: {name}",
            f"type: {memory_type}",
            f"description: {description or name}",
            f"agent: {self._agent_name}",
            f"scope: team",
            "---",
            "",
        ]

        try:
            filepath.write_text(
                "\n".join(frontmatter_lines) + content, encoding="utf-8"
            )
            return True
        except OSError:
            return False

    def list_team_memory_files(self, scope: MemoryScope = MemoryScope.PROJECT) -> list[dict]:
        team_dir = self._get_team_memory_dir(scope)
        if not team_dir.exists():
            return []

        results = []
        for f in sorted(team_dir.glob("*.md")):
            try:
                raw = f.read_text(encoding="utf-8")
                meta = {"name": f.stem, "scope": "team", "path": str(f)}
                if raw.startswith("---"):
                    end = raw.find("---", 3)
                    if end != -1:
                        header = raw[3:end].strip()
                        for line in header.split("\n"):
                            if ":" in line:
                                k, v = line.split(":", 1)
                                meta[k.strip()] = v.strip()
                meta["size"] = len(raw)
                meta["is_expired"] = _is_memory_expired(f)
                results.append(meta)
            except (OSError, UnicodeDecodeError):
                continue
        return results

    def save_team_memory(self, content: str, scope: MemoryScope = MemoryScope.PROJECT) -> bool:
        team_dir = self._get_team_memory_dir(scope)
        try:
            team_dir.mkdir(parents=True, exist_ok=True)
            lines = content.split("\n")
            if len(lines) > MEMORY_MAX_LINES:
                content = "\n".join(lines[:MEMORY_MAX_LINES])
            if len(content.encode("utf-8")) > MEMORY_MAX_SIZE:
                content = content.encode("utf-8")[:MEMORY_MAX_SIZE].decode("utf-8", errors="ignore")
            target_file = team_dir / "MEMORY.md"
            target_file.write_text(content, encoding="utf-8")
            return True
        except OSError:
            return False


def validate_memory_path(path: str) -> bool:
    if not path:
        return False

    if "\x00" in path:
        return False

    if ".." in Path(path).parts:
        return False

    if "\\" in path and not Path(path).is_absolute():
        return False

    cleaned = path.replace("\\", "/")
    if "/../" in cleaned or cleaned.startswith("../") or cleaned.endswith("/.."):
        return False

    return True


def _is_memory_expired(file_path: Path) -> bool:
    try:
        import os as _os
        mtime = _os.path.getmtime(str(file_path))
        age_days = (time.time() - mtime) / 86400
        return age_days > MEMORY_EXPIRY_DAYS
    except OSError:
        return False


def _check_save_exclusion(content: str) -> list[str]:
    warnings = []
    lower = content.lower()

    exclusion_patterns = [
        (r"(文件路径|目录结构|src/|lib/|app/)", "代码路径/结构信息"),
        (r"(git\s+(log|commit|branch|merge|rebase))", "Git 操作历史"),
        (r"(debug|调试|修复了?|bug\s*fix)", "调试解决方案"),
        (r"(进行中|wip|todo|临时)", "临时任务细节"),
    ]

    for pattern, desc in exclusion_patterns:
        if re.search(pattern, lower):
            warnings.append(desc)

    return warnings


def memory_age(file_path: Path) -> str:
    import os
    try:
        mtime = os.path.getmtime(str(file_path))
        age_seconds = time.time() - mtime
        age_days = int(age_seconds / 86400)
        if age_days == 0:
            return "today"
        elif age_days == 1:
            return "yesterday"
        elif age_days < 30:
            return f"{age_days} days ago"
        elif age_days < 365:
            return f"{age_days // 30} months ago"
        else:
            return f"{age_days // 365} years ago"
    except OSError:
        return "unknown"


def memory_freshness_text(file_path: Path) -> str:
    age = memory_age(file_path)
    if age in ("today", "yesterday", "unknown"):
        return ""
    return f"(This memory is {age})"


def memory_freshness_note(file_path: Path) -> str:
    text = memory_freshness_text(file_path)
    if not text:
        return ""
    return f"<system-reminder>{text}</system-reminder>"


def get_daily_log_path(memory_dir: Path, date: str | None = None) -> Path:
    import datetime
    if date is None:
        date = datetime.date.today().isoformat()
    daily_dir = memory_dir / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    return daily_dir / f"{date}.md"


def append_to_daily_log(
    memory_dir: Path,
    content: str,
    scope: MemoryScope = MemoryScope.PROJECT,
    date: str | None = None,
) -> bool:
    log_path = get_daily_log_path(memory_dir, date)
    try:
        timestamp_header = ""
        if not log_path.exists():
            timestamp_header = f"# Daily Log - {date or 'today'}\n\n"

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(timestamp_header)
            f.write(f"## {time.strftime('%H:%M')}\n{content}\n\n")
        return True
    except OSError:
        return False


def archive_daily_log(memory_dir: Path, date: str) -> bool:
    log_path = get_daily_log_path(memory_dir, date)
    if not log_path.exists():
        return False

    archive_dir = memory_dir / "daily" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    try:
        target = archive_dir / f"{date}.md"
        log_path.rename(target)
        return True
    except OSError:
        return False


EXTRACT_MEMORIES_PROMPT = """分析以下对话内容，提取值得长期保存的记忆。

规则：
1. 只保存不可从代码/项目推导的信息
2. 不保存临时状态或进行中的工作
3. 不保存已在 CLAWS.md 中文档化的内容
4. 每条记忆包含：类型(user/feedback/project/reference)、内容、是否团队共享

输出格式：
- type: <类型>
- content: <内容>
- shared: <true/false>
"""


class ExtractMemoriesAgent:
    ALLOWED_TOOLS = ["FileRead", "FileWrite", "Glob", "Grep"]

    def __init__(self, memory: AgentMemory) -> None:
        self._memory = memory

    def extract_from_messages(self, messages: list[dict]) -> list[dict]:
        conversation_text = self._summarize_messages(messages)
        if not conversation_text:
            return []

        potential_memories = self._analyze_conversation(conversation_text)
        validated = self._validate_memories(potential_memories)
        return validated

    def _summarize_messages(self, messages: list[dict]) -> str:
        parts = []
        for msg in messages[-20:]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if content and isinstance(content, str):
                parts.append(f"[{role}]: {content[:500]}")
        return "\n".join(parts)

    def _analyze_conversation(self, text: str) -> list[dict]:
        lower = text.lower()
        memories = []

        preference_patterns = [
            (r"(偏好|喜欢|prefer|like)\s+(.+?)(?:[。，.]|$)", "user"),
            (r"(不要|避免|don't|avoid)\s+(.+?)(?:[。，.]|$)", "feedback"),
            (r"(项目|project|架构|architecture)\s+(.+?)(?:[。，.]|$)", "project"),
        ]

        import re
        for pattern, mem_type in preference_patterns:
            for match in re.finditer(pattern, lower):
                content = match.group(0)
                if _check_save_exclusion(content):
                    continue
                memories.append({
                    "type": mem_type,
                    "content": content,
                    "shared": mem_type in ("project", "reference"),
                })

        return memories[:5]

    def _validate_memories(self, memories: list[dict]) -> list[dict]:
        validated = []
        for mem in memories:
            content = mem.get("content", "")
            if len(content) < 10:
                continue
            if _check_save_exclusion(content):
                continue
            validated.append(mem)
        return validated
