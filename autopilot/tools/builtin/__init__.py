from autopilot.tools.base import Tool
from autopilot.tools.builtin.apply_patch import ApplyPatchTool
from autopilot.tools.builtin.glob import GlobTool
from autopilot.tools.builtin.grep import GrepTool
from autopilot.tools.builtin.read_file import ReadFileTool
from autopilot.tools.builtin.todo import TodosTool
from autopilot.tools.builtin.web_fetch import WebFetchTool
from autopilot.tools.builtin.web_search import WebSearchTool
from autopilot.tools.builtin.write_file import WriteFileTool
from autopilot.tools.builtin.edit_file import EditFileTool
from autopilot.tools.builtin.shell import ShellTool
from autopilot.tools.builtin.list_dir import ListDirTool
from autopilot.tools.builtin.memory import MemoryTool
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
    "TodosTool",
    "MemoryTool",
    "ApplyPatchTool"
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
        TodosTool,
        MemoryTool,
        ApplyPatchTool
    ]
