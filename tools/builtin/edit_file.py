from pathlib import Path
from tools.base import FileDiff, Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult
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


class EditFileTool(Tool):
    name = "edit_file"
    description = (
        "Always call read_file first unless you are absolutely certain of the file contents."
        "Edit a file by replacing text. The old_string must match exactly"
        "(including whitespace and indentation) and must be unique in the file"
        "unless replace_all is true. Use this for precise, surgical edits"
        "For creating new files or complete rewrites, use write_file instead"
    )
    kind = ToolKind.WRITE

    @property
    def schema(self):
        return EditParams

    async def get_confirmation(self, invocation: ToolInvocation) -> ToolConfirmation | None:
        params = EditParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        is_new_file = not path.exists()

        if is_new_file:
            diff = FileDiff(
                path=path,
                old_content="",
                new_content=params.new_string,
                is_new_file=True
            )

            return ToolConfirmation(
                tool_name=self.name,
                params=invocation.params,
                description=f"Create new file: {path}",
                diff=diff,
                affected_paths=[path],
            )

        old_content = path.read_text(encoding="utf-8")

        if params.replace_all:
            new_content = old_content.replace(params.old_string, params.new_string)
        else:
            new_content = old_content.replace(params.old_string, params.new_string, 1)

        diff = FileDiff(
            path=path,
            old_content=old_content,
            new_content=new_content,
        )

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"Edit file: {path}",
            diff=diff,
            affected_paths=[path],
            # overwriting is more dangerous than writing a new file (user old content might get lost so)
            is_dangerous=not is_new_file)

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
        old_content = path.read_text(encoding="utf-8")

        # file exist kar rha, but content hi nai hai, to error hai.. yaa to purana content do, ya naya file banao
        if not params.old_string:
            return ToolResult.error_result(
                f"old_string is empty but file exists. Provide old_string to edit, or use write_file instead"
            )

        occurence_count = old_content.count(params.old_string)
        # jo text hame replace karna tha, voh mila hi nai
        # "a + b" tha file mai, LLM nai "a+b" diya, fir bhi galat hi hai
        if occurence_count == 0:
            return self.recover_on_no_match_error(params.old_string, old_content, path)

        if occurence_count > 1 and not params.replace_all:
            # 3 print("hello") statements use kiye debugging ke liye, hume nai pata konsa replace karna hai, to yaa to jyaada context chahiye ya fir saare replace karvado
            return ToolResult.error_result(
                f"old_string found {occurence_count} times in {path}"
                f"Either: \n"
                f"1. Provide more context to make the match unique or \n"
                f"2. Set replace_all=true to replace all occurences",
                metadata={
                    "occurence_count": occurence_count
                }
            )
        replace_count = 0
        new_content = ""

        if params.replace_all:
            new_content = old_content.replace(params.old_string, params.new_string)
            # replacing every occurence
            replace_count = occurence_count
        else:
            new_content = old_content.replace(params.old_string, params.new_string, 1)
            # replacing only the first occurence
            replace_count = 1

        if new_content == old_content:
            # stopping agent from infinite loops and wasting tokens
            return ToolResult.error_result("No change made - old_string equals new string")

        try:
            path.write_text(new_content, encoding="utf-8")
        except IOError as e:
            return ToolResult.error_result(f"failed to write file : {e}")

        old_lines = len(old_content.splitlines())
        new_lines = len(new_content.splitlines())
        line_diff = old_lines-new_lines

        diff_msg = ""

        if line_diff > 0:
            diff_msg = f" (+{line_diff}) lines"
        elif line_diff < 0:
            diff_msg = f" (-{line_diff}) lines"

        return ToolResult.success_result(
            f"Edited {path}: replaced {replace_count} occurence(s) {diff_msg}",
            diff=FileDiff(
                path=path,
                old_content=old_content,
                new_content=new_content
            ),
            metadata={
                "path": str(path),
                "replace_count": replace_count,
                "line_diff": line_diff
            }
        )

    # to help the LLM to recover if it didn't find any matching text

    def recover_on_no_match_error(self, old_string: str, content: str, path: Path) -> ToolResult:
        lines = content.splitlines()

        partial_matches = []  # contains line_number and preview of line

        # take first 5 letters from each old_string phrase
        # to enhance the search
        search_terms = old_string.split()[:5]

        if search_terms:
            first_term = search_terms[0]  # generally first_term is the most useful keyword
            for i, line in enumerate(lines, 1):
                if first_term in line:
                    # stripping to remove whitespaces and taking the first 80 characters
                    partial_matches.append((i, line.strip()[:80]))
                    if len(partial_matches) >= 3:
                        break

        error_msg = f"old_string not found in {path}"

        if partial_matches:
            error_msg += "\n\nPossible similar lines:"
            # redirecting the LLM to think according to the partial matches (if present)
            for line_num, line_preview in partial_matches:
                error_msg += f"\n line {line_num}: {line_preview}"
            error_msg += (
                "\n\nMake sure old_string matches exactly (including whitespace) "
            )
        else:
            # else being more strict and comprehensive and telling it to find text more properly
            error_msg += (
                "Make sure the text matches exactly, including:\n"
                "- All whitespace and indentation"
                "- Line breaks"
                "- Any invisible characters"
                "Try re-reading the file using read_file tool and then editing"
            )

        return ToolResult.error_result(error_msg)
