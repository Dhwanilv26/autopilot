import os
from pathlib import Path

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from utils.paths import is_binary_file, resolve_path


IGNORED_DIRS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv"
}


class GlobParams(BaseModel):
    pattern: str = Field(
        ...,
        description="Glob pattern to match (e.g. *.py or **/*.py)."
    )

    path: str = Field(
        ".",
        description="Directory to search in (default: current directory)"
    )


class GlobTool(Tool):
    name = "glob"
    description = "Find files matching a glob pattern. Supports recursive matching using **."
    kind = ToolKind.READ

    @property
    def schema(self):
        return GlobParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GlobParams(**invocation.params)

        search_path = resolve_path(invocation.cwd, params.path)

        if not search_path.exists() or not search_path.is_dir():
            return ToolResult.error_result(
                f"Directory does not exist: {search_path}"
            )

        try:
            
            if "**" in params.pattern:
                matches = list(search_path.rglob(params.pattern.replace("**/", "")))
            else:
                matches = list(search_path.glob(params.pattern))

            
            filtered = []
            for p in matches:
                if not p.is_file():
                    continue

                if any(part in IGNORED_DIRS for part in p.parts):
                    continue

                if is_binary_file(p):
                    continue

                filtered.append(p)

        except Exception as e:
            return ToolResult.error_result(f"Error searching: {e}")

        
        if not filtered:
            return ToolResult.error_result(
                f"No files found for pattern: {params.pattern}",
                metadata={
                    "path": str(search_path),
                    "matches": 0
                }
            )

        
        output_lines = []
        for file_path in filtered[:200]:  
            try:
                rel_path = file_path.relative_to(invocation.cwd)
            except Exception:
                rel_path = file_path

            output_lines.append(str(rel_path))

        return ToolResult.success_result(
            "\n".join(output_lines),
            metadata={
                "path": str(search_path),
                "matches": len(filtered)
            }
        )
