from tools.base import FileDiff, Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from utils.paths import ensure_parent_directory, resolve_path


class EditParams(BaseModel):
    path: str = Field(
        ...,
        description="Path to the file to edit (relative to working directory or absolute)"
    )
    old_string: str = Field(
        "",
        description="The exact text to find and replace. Must match exactly including all whitespace and indentation. For new files, leave this empty."
    )
    new_string: str = Field(
        "",
        description="The text to replace old_string with. Can be empty to delete text."
    )
    replace_all: bool = Field(
        False,
        description="Replace all occurences of old_string (default: false)"
    )


class EditTool(Tool):
    name = "edit"
    description = (
        "Edit a file by replacing text. The old_string must match exactly"
        "(including whitespace and indentation) and must be unique in the file"
        "unless replace_all is true. Use this for precise, surgical edits"
        "For creating new files or complete rewrites, use write_file instead"
    )
    kind = ToolKind.WRITE

    @property
    def schema(self):
        return EditParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = EditParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        if not path.exists():
        # creating a new file and then using the same logic as write_file
            if params.old_string:
                return ToolResult.error_result(
                    f"File does not exist : {path}. To create a new file, use an empty old string instead"
                )
            ensure_parent_directory(path)
            path.write_text(params.new_string, encoding="utf-8")

            line_count = len(params.new_string.splitlines())

            return ToolResult.success_result(
                f"Created {path} {line_count} lines",
                diff=FileDiff(
                    path=path,
                    old_content="",
                    new_content=params.new_string,
                    is_new_file=True
                ),
                metadata={
                    "path": str(path),
                    "is_new_file": True,
                    "lines": line_count
                }
            )
