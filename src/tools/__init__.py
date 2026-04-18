from __future__ import annotations

from src.tool import Tool


def get_tools() -> list[Tool]:
    from src.tools.agent import AgentTool
    from src.tools.ask_user import AskUserQuestionTool
    from src.tools.bash import BashTool
    from src.tools.config_tool import ConfigTool
    from src.tools.file_edit import FileEditTool
    from src.tools.file_read import FileReadTool
    from src.tools.file_write import FileWriteTool
    from src.tools.glob import GlobTool
    from src.tools.grep import GrepTool
    from src.tools.send_message import SendMessageTool
    from src.tools.sleep_tool import SleepTool
    from src.tools.task_output import TaskOutputTool
    from src.tools.task_stop import TaskStopTool
    from src.tools.todo_write import TodoWriteTool
    from src.tools.tool_search import ToolSearchTool
    from src.tools.web_fetch import WebFetchTool
    from src.tools.web_search import WebSearchTool
    from src.agents.swarm import TeamCreateTool, TeamDeleteTool, TeamListTool, SwarmDispatchTool

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
        TaskOutputTool(),
        TaskStopTool(),
        TeamCreateTool(),
        TeamDeleteTool(),
        TeamListTool(),
        SwarmDispatchTool(),
    ]

    return [t for t in tools if t.is_available()]
