from __future__ import annotations

from src.tool import Tool


def get_tools() -> list[Tool]:
    from src.tools.agent import AgentTool
    from src.tools.ask_user import AskUserQuestionTool
    from src.tools.bash import BashTool
    from src.tools.config_tool import ConfigTool
    from src.tools.enter_plan import EnterPlanModeTool
    from src.tools.exit_plan import ExitPlanModeTool
    from src.tools.file_edit import FileEditTool
    from src.tools.file_read import FileReadTool
    from src.tools.file_write import FileWriteTool
    from src.tools.glob import GlobTool
    from src.tools.grep import GrepTool
    from src.tools.send_message import SendMessageTool
    from src.tools.skill_tool import SkillTool
    from src.tools.sleep_tool import SleepTool
    from src.tools.task_output import TaskOutputTool
    from src.tools.task_stop import TaskStopTool
    from src.tools.todo_write import TodoWriteTool
    from src.tools.tool_search import ToolSearchTool
    from src.tools.web_fetch import WebFetchTool
    from src.tools.web_search import WebSearchTool
    from src.agents.swarm import TeamCreateTool, TeamDeleteTool, TeamListTool, SwarmDispatchTool
    from src.tools.brief import BriefTool
    from src.tools.notebook_edit import NotebookEditTool
    from src.tools.lsp_tool import LSPTool
    from src.tools.powershell import PowerShellTool
    from src.tools.cron_create import CronCreateTool
    from src.tools.cron_delete import CronDeleteTool
    from src.tools.cron_list import CronListTool
    from src.tools.workflow import WorkflowTool
    from src.tools.mcp_auth import McpAuthTool
    from src.tools.list_mcp_resources import ListMcpResourcesTool
    from src.tools.read_mcp_resource import ReadMcpResourceTool
    from src.tools.computer_use import (
        BrowserScreenshotTool,
        BrowserMouseClickTool,
        BrowserMouseMoveTool,
        BrowserDragTool,
        BrowserScrollTool,
        BrowserKeyboardTool,
        BrowserNavigateTool,
        BrowserLaunchTool,
        BrowserConnectTool,
        BrowserShutdownTool,
    )

    tools = [
        AgentTool(),
        BashTool(),
        FileEditTool(),
        FileReadTool(),
        FileWriteTool(),
        GlobTool(),
        GrepTool(),
        WebFetchTool(),
        WebSearchTool(),
        TodoWriteTool(),
        AskUserQuestionTool(),
        ConfigTool(),
        ToolSearchTool(),
        SleepTool(),
        SendMessageTool(),
        SkillTool(),
        TaskOutputTool(),
        TaskStopTool(),
        EnterPlanModeTool(),
        ExitPlanModeTool(),
        TeamCreateTool(),
        TeamDeleteTool(),
        TeamListTool(),
        SwarmDispatchTool(),
        BriefTool(),
        NotebookEditTool(),
        LSPTool(),
        PowerShellTool(),
        CronCreateTool(),
        CronDeleteTool(),
        CronListTool(),
        WorkflowTool(),
        McpAuthTool(),
        ListMcpResourcesTool(),
        ReadMcpResourceTool(),
        BrowserScreenshotTool(),
        BrowserMouseClickTool(),
        BrowserMouseMoveTool(),
        BrowserDragTool(),
        BrowserScrollTool(),
        BrowserKeyboardTool(),
        BrowserNavigateTool(),
        BrowserLaunchTool(),
        BrowserConnectTool(),
        BrowserShutdownTool(),
    ]

    return [t for t in tools if t.is_available()]
