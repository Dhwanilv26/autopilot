import os
from pathlib import Path

from autopilot.tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from autopilot.utils.paths import is_binary_file, resolve_path

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

    case_insensitive: bool = Field(
        False,
        description="Case-insensitive search (default:False)"
    )


class GrepTool(Tool):
    name = "grep"
    description = "Search for a regex pattern in the file contents. Returns matching lines with file paths and line numbers." \
    "Always use correct absolute path."
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
            flags = re.IGNORECASE if params.case_insensitive else 0
            pattern = re.compile(params.pattern, flags)
        except re.error as e:
            return ToolResult.error_result(f"Invalid regex pattern : {e}")

        if search_path.is_dir():
            files = self._find_files(search_path)
        else:
            files = [search_path]

        output_lines = []
        matches = 0

        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                continue

            lines = content.splitlines()
            file_matches = False
            for i, line in enumerate(lines, start=1):
                if pattern.search(line):
                    matches += 1
                    if not file_matches:
                        rel_path = file_path.relative_to(invocation.cwd)
                        output_lines.append(f"==={rel_path}===")
                        file_matches = True

                    output_lines.append(f"{i}: {line}")

                if file_matches:
                    output_lines.append("")

        if not output_lines:
            return ToolResult.error_result(
                f"no matches found for pattern {params.pattern}",
                metadata={
                    "path": str(search_path),
                    "matches": 0,
                    "files_searched": len(files)
                })

        return ToolResult.success_result(
            "\n".join(output_lines),
            metadata={
                "path": str(search_path),
                "matches": matches,
                "files_searched": len(files)
            }
        )

    def _find_files(self, search_path: Path) -> list[Path]:
        # just to search all the files
        files = []
        for root, dirs, filenames in os.walk(search_path):
            # replacing the entire content list and ignoring these bullshit files (slice operator)
            # os.walk() works on pass by reference
            dirs[:] = [d
                       for d in dirs
                       if d not in {
                           "node_modules", "__pycache", ".git", ".venv", "venv"}]
            for filename in filenames:
                if filename.startswith("."):
                    continue
                # ignore unwanted folders and convert to absolute path (of non binary files)
                file_path = Path(root)/(filename)
                if not is_binary_file(file_path):
                    files.append(file_path)
                    if len(files) >= 500:
                        return files  # just truncating the output

        return files
