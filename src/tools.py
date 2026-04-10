from __future__ import annotations

from src.tool import Tool


def get_tools() -> list[Tool]:
    from src.tools.bash import BashTool
    from src.tools.file_edit import FileEditTool
    from src.tools.file_read import FileReadTool
    from src.tools.glob import GlobTool
    from src.tools.grep import GrepTool

    return [BashTool(), FileEditTool(), FileReadTool(), GlobTool(), GrepTool()]
