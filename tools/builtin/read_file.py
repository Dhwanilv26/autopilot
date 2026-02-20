from pydantic import BaseModel, Field

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from utils.paths import resolve_path


class ReadFileParams(BaseModel):
    # ... means the field is required, this field is from pydantic, used in the same manner like z.object() and not from python to create new default_dict
    path: str = Field(
        ...,
        description="Path to the file to read (relative to working directory or absolute path)")
    offset: int = Field(
        1, ge=1, description="Line number to start reading from (1-based). Defaults to 1")
    limit: int | None = Field(
        None, ge=1, description="Maximum number of lines to read. If not specified, read entire file ")


class ReadFileTool(Tool):
    name = "read_file"
    # to concatenate multiple strings
    description = (
        "Read the contents of a text file. Returns the file content with the line numbers."
        "For large files, use offset and limit to read specific portions."
        "Do not read binary files (images, executables, etc.)."
    )
    kind = ToolKind.READ

    schema = ReadFileParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        # destructuring the invocation.params and putting into readfileparams format
        params = ReadFileParams(**invocation.params)
        # current working directory is invocation.cwd and params.path is the file path for which the real_file tool is gonna be applied
        path = resolve_path(invocation.cwd, params.path)

        if not path.exists():
            return ToolResult.error_result(f"File not found: {path}")

        if not path.is_file():
            return ToolResult.error_result(f"Path is not a file: {path}")
