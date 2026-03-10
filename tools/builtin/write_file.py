from pydantic import BaseModel, Field
from tools.base import FileDiff, Tool, ToolInvocation, ToolKind, ToolResult
from utils.paths import ensure_parent_directory, resolve_path


class WriteFileParams(BaseModel):
    # these are the actual params for the tool, ... means field is required and has no default value
    path: str = Field(
        ...,
        description="Path to the file to write (relatvie to working directory or absolute)")
    content: str = Field(
        ...,
        description="Content to write to file")
    create_directories: bool = Field(
        True, description="Create parent directories if they exist"
    )


class WriteFileTool(Tool):
    name = "write_file"
    # this description acts as a system prompt for the tool
    description = (
        "Write content to a file. Creates the file if it does not exist,"
        "or overwrites if it does. Parent directories are created automatically"
        "Use this for creating new files or completely replacing file contents"
        "For partial modifications, use the edit tool instead"
    )
    kind = ToolKind.WRITE

    @property
    def schema(self):
        return WriteFileParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WriteFileParams(**invocation.params)
        # invo.cwd -> current folder, params.path -> destn folder
        path = resolve_path(invocation.cwd, params.path)

        is_new_file = not path.exists()
        old_content = ""  # used to display diffs or compare changes

        if not is_new_file:
            try:
                old_content = path.read_text(encoding="utf-8")
            except:
                pass

        try:
            if params.create_directories:
                ensure_parent_directory(path)  # create a new path if not present
            elif not path.parent.exists():
                return ToolResult.error_result(f"Parent directory does not exists: {path.parent}")

            # the actual file is created here, with the text, and if the file is already present, the file is overwritten
            path.write_text(params.content, encoding="utf-8")

            action = "Created" if is_new_file else "updated"
            line_count = len(params.content.splitlines())

            return ToolResult.success_result(
                f" {action} {path} {line_count} lines",
                diff=FileDiff(
                    path=path,
                    old_content=old_content,
                    new_content=params.content,
                    is_new_file=is_new_file
                ),
                metadata={
                    'path': str(path),
                    "is_new_file": is_new_file,
                    "lines": line_count,
                    "bytes": len(params.content.encode("utf-8"))
                }
            )

        except OSError as e:
            return ToolResult.error_result(f"Failed to write file : {e}")
