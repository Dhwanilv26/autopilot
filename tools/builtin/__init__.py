from tools.base import Tool
from tools.builtin.glob import GlobTool
from tools.builtin.grep import GrepTool
from tools.builtin.read_file import ReadFileTool
from tools.builtin.todo import TodosTool
from tools.builtin.web_fetch import WebFetchTool
from tools.builtin.web_search import WebSearchTool
from tools.builtin.write_file import WriteFileTool
from tools.builtin.edit_file import EditFileTool
from tools.builtin.shell import ShellTool
from tools.builtin.list_dir import ListDirTool
_all_ = [
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool"
    "ShellTool",
    "ListDirTool",
    "GrepTool",
    "GlobTool",
    "WebSearchTool",
    "WebFetchTool",
    "TodosTool"
]


def get_all_builtin_tools() -> list[type[Tool]]:
    return [
        ReadFileTool,
        WriteFileTool,
        EditFileTool,
        ShellTool,
        ListDirTool,
        GrepTool,
        GlobTool,
        WebSearchTool,
        WebFetchTool,
        TodosTool
    ]
