from pathlib import Path
from pydantic import BaseModel, Field

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from utils.paths import resolve_path


IGNORED_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv"
}


class ListDirParams(BaseModel):
    path: str = Field(
        ".",
        description="Directory path to list (default: current directory)"
    )

    include_hidden: bool = Field(
        False,
        description="Include hidden files and directories"
    )

    recursive: bool = Field(
        True,
        description="Recursively explore directories"
    )

    max_depth: int = Field(
        5,
        description="Maximum recursion depth"
    )


class ListDirTool(Tool):
    name = "list_dir"
    description = "List contents of a directory with optional recursive tree view"
    kind = ToolKind.READ

    @property
    def schema(self):
        return ListDirParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ListDirParams(**invocation.params)

        root = resolve_path(invocation.cwd, params.path)

        if not root.exists() or not root.is_dir():
            return ToolResult.error_result(
                f"Directory does not exist: {root}"
            )

        lines = [f"{root.name}/"]
        entries = 0

        try:
            if params.recursive:
                entries = self._build_tree(
                    root,
                    lines,
                    prefix="",
                    include_hidden=params.include_hidden,
                    depth=0,
                    max_depth=params.max_depth
                )
            else:
                items = sorted(
                    root.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.lower())
                )

                if not params.include_hidden:
                    items = [i for i in items if not i.name.startswith(".")]

                for item in items:
                    if item.is_dir():
                        lines.append(f"🗂️ {item.name}/")
                    else:
                        lines.append(item.name)

                entries = len(items)

        except Exception as e:
            return ToolResult.error_result(
                f"Error listing directory: {e}"
            )

        if entries == 0:
            return ToolResult.success_result(
                "directory is empty",
                metadata={
                    "path": str(root),
                    "entries": 0,
                    "recursive": params.recursive
                }
            )

        return ToolResult.success_result(
            "\n".join(lines),
            metadata={
                "path": str(root),
                "entries": entries,
                "recursive": params.recursive,
                "max_depth": params.max_depth
            }
        )

    def _build_tree(
        self,
        directory: Path,
        lines: list[str],
        prefix: str,
        include_hidden: bool,
        depth: int,
        max_depth: int
    ) -> int:

        if depth >= max_depth:
            return 0

        try:
            items = sorted(
                directory.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower())
            )
        except Exception:
            return 0

        if not include_hidden:
            items = [i for i in items if not i.name.startswith(".")]

        total = len(items)
        count = 0

        for index, item in enumerate(items):

            connector = "└── " if index == total - 1 else "├── "

            # Handle ignored directories
            if item.is_dir() and item.name in IGNORED_DIRS:
                lines.append(f"{prefix}{connector}{item.name}/ (skipped)")
                count += 1
                continue

            if item.is_dir():
                lines.append(f"{prefix}{connector}{item.name}/")
            else:
                lines.append(f"{prefix}{connector}{item.name}")

            count += 1

            if item.is_dir():
                extension = "    " if index == total - 1 else "│   "

                count += self._build_tree(
                    item,
                    lines,
                    prefix + extension,
                    include_hidden,
                    depth + 1,
                    max_depth
                )

        return count
