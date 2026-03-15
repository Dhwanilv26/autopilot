import os
from pathlib import Path

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from utils.paths import is_binary_file, resolve_path

import re


class GrepParams(BaseModel):
    pattern: str = Field(
        ...,
        description="Regular expression pattern to search for."
    )

    path: str = Field(
        ".",
        description="File or directory to search in (default: current directory)"
    )

    case_insenstive: bool = Field(
        False,
        description="Case-insensitive search (default:False)"
    )


class GrepTool(Tool):
    name = "grep"
    description = "Search for a regex pattern in the file contents. Returns matching lines with file paths and line numbers."
    kind = ToolKind.READ

    @property
    def schema(self):
        return GrepParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GrepParams(**invocation.params)

        search_path = resolve_path(invocation.cwd, params.path)

        if not search_path.exists():
            return ToolResult.error_result(f"Grep search_path does not exist :  {search_path}")

        try:
            flags = re.IGNORECASE if params.case_insenstive else 0
            pattern = re.compile(params.pattern, flags)
        except re.error as e:
            return ToolResult.error_result(f"Invalid regex pattern : {e}")

        if search_path.is_dir():
            files = self._find_files(search_path)
        else:
            files = [search_path]

    def _find_files(self, search_path: Path) -> list[Path]:

        files = []
        for root, dirs, filenames in os.walk(search_path):
            for filename in filenames:
                if filename.startswith("."):
                    continue

                file_path = Path[root]/(filename)
                if not is_binary_file(file_path):
                    files.append(file_path)
                    if len(files) >= 500:
                        return files  # just truncating the output

        return files
