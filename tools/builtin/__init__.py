from tools.base import Tool
from tools.builtin.read_file import ReadFileTool
_all_ = [
    "ReadFileTool"
]


def get_all_builtin_tools() -> list[type[Tool]]:
    return [
        ReadFileTool,
    ]
