from pydantic import BaseModel, Field

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from utils.paths import is_binary_file, resolve_path
from utils.text import count_tokens, truncate_text


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

    # schema is a property in the basetool class, so it should also be implemented as a property in the subsequent child classes too
    @property
    def schema(self):
        return ReadFileParams  # returning just the type of the class, exactly what is required in the basetool

    MAX_FILE_SIZE = 1024*1024*10  # 10 MB MAX
    MAX_OUTPUT_TOKENS = 250000

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        # destructuring the invocation.params and putting into readfileparams format
        params = ReadFileParams(**invocation.params)
        # current working directory is invocation.cwd and params.path is the file path for which the real_file tool is gonna be applied
        path = resolve_path(invocation.cwd, params.path)

        if not path.exists():
            return ToolResult.error_result(f"File not found: {path}")

        if not path.is_file():
            return ToolResult.error_result(f"Path is not a file: {path}")

        file_size = path.stat().st_size

        if file_size > self.MAX_FILE_SIZE:
            return ToolResult.error_result(
                f"File is too large ({file_size/(1024*1024):.1f}MB)."
                f"Maximum is {self.MAX_FILE_SIZE/(1024*1024):.0f}MB")

        if is_binary_file(path):
            file_size_mb = file_size / (1024 * 1024)
            size_str = (
                f"{file_size_mb:.2f}MB" if file_size_mb >= 1 else f"{file_size} bytes"
            )
            return ToolResult.error_result(
                f"Cannot read binary file : {path.name} ({size_str})"
                f"This tool only reads text files."
            )
        try:

            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="latin-1")

            lines = content.splitlines()
            total_lines = len(lines)

            if total_lines == 0:
                return ToolResult.success_result(
                    "File is empty",
                    metadata={"lines": 0}
                )
            # lines is an array here, so using indexes here
            start_idx = max(0, params.offset-1)

            if params.limit is not None:
                end_idx = min(start_idx + params.limit, total_lines)
            else:
                end_idx = total_lines

            # start_idx is 0 based, end_idx is 1 based, so no need to worry about the slice operator
            selected_lines = lines[start_idx:end_idx]
            formatted_lines = []

            for i, line in enumerate(selected_lines, start=start_idx):
                # editor like feel (10 | print("hello world"))
                # :6 used for right aligning numbers before |
                formatted_lines.append(f"{i:6}|{line}")

            output = "\n".join(formatted_lines)
            token_count = count_tokens(output, "qwen/qwen3-vl-30b-a3b-thinking")

            truncated = False

            if token_count > self.MAX_OUTPUT_TOKENS:
                output = truncate_text(
                    text=output,
                    model="qwen/qwen3-vl-30b-a3b-thinking",
                    max_tokens=self.MAX_OUTPUT_TOKENS,
                    suffix=f"\n... [truncated {total_lines} total lines]",
                    preserve_lines=False
                )
                truncated = True
            metadata_lines = []
            if start_idx > 0 or end_idx < total_lines:
                metadata_lines.append(
                    f"showing lines {start_idx+1} -{end_idx} of {total_lines} {total_lines} lines")

            if metadata_lines:
                header = " | ".join(metadata_lines) + "\n\n"
                output = header+output

            return ToolResult.success_result(
                output=output,
                truncated=truncated,
                metadata={
                    "path": str(path),
                    "total_lines": total_lines,
                    "shown_start": start_idx+1,
                    "shown_end": end_idx
                }
            )
        except Exception as e:
            return ToolResult.error_result(f"Failed to read file:{e}")
