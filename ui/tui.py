from pathlib import Path
from typing import Any, Tuple

from rich.console import Console
from rich.theme import Theme
from rich.rule import Rule
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.syntax import Syntax
from rich.console import Group
from rich.markdown import Markdown
from rich.style import Style
import re  # importing regex

from utils.markdown import normalize_markdown

from utils.paths import display_path_rel_to_cwd, resolve_path
from utils.text import truncate_text

from config.config import Config
AGENT_THEME = Theme(
    {
        # General - Using a mix of professional and alert neons
        # "info": "dodger_blue1",
        "info": "#ff8c42",
        "warning": "orange1",
        "error": "bright_red bold",
        "success": "spring_green3",
        "dim": "grey37",
        "muted": "grey42",
        "border": "grey27",
        "highlight": "underline bold #ff8c42",

        # Roles - Strong contrast between User and Assistant
        "user": "deep_sky_blue1 bold",
        # "assistant": "bright_white",

        "assistant": "bold #ff8c42",
        "assistant.text": "#ff8c42",


        "markdown.heading": "bold #ff8c42",
        "markdown.bold": "bold #ff8c42",
        "markdown.code": "#ff8c42",
        "markdown.item": "white",
        "markdown.block_quote": "dim",

        "code": "grey93",

        # Tools - Vibrant neons to distinguish from regular text
        "tool": "medium_purple1 bold",
        "tool.read": "aquamarine1",
        "tool.write": "gold1",
        "tool.shell": "bright_magenta",
        "tool.network": "cornflower_blue",
        "tool.memory": "sea_green1",
        "tool.mcp": "cyan2",

    }
)
# jaanbuchkar private rkaha taaki globally sirf ek hi instance bane and dusre files sirf get_console() se hi access kar paayenge saara
_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        # _console = Console(theme=AGENT_THEME, highlight=False)
        _console = Console(theme=AGENT_THEME,
                           highlight=True,
                           markup=True,
                           soft_wrap=True,
                           force_terminal=True)

    return _console


class TUI:
    def __init__(self, console: Console | None = None) -> None:
        self.console = _console or get_console()
        self._assistant_stream_open = False
        self._assistant_buffer: str = ""
        # call id and all args for that tool, used for caching as they are needed in multiple event displays in the tui
        self._tool_args_by_call_id: dict[str, dict[str, Any]] = {}
        self.cwd = Path.cwd()
        self.config = Config

    def begin_assistant(self) -> None:
        self.console.print()  # for new line
        # self.console.print(Rule(Text("Assistant", style="assistant")))
        self._assistant_stream_open = True
        self._assistant_buffer = ""

    def end_assistant(self) -> None:
        if not self._assistant_stream_open:
            return

        self.console.print()

        cleaned_text = normalize_markdown(self._assistant_buffer)

        self.console.print()

        md = Markdown(cleaned_text, code_theme="monokai")

        panel = Panel(
            md,
            title=Text("Assistant", style="assistant"),
            border_style="success",
            padding=(1, 2),
            box=box.ROUNDED,
            expand=True
        )

        self.console.print(panel)

        self._assistant_stream_open = False
        self._assistant_buffer = ""

    def stream_assistant_delta(self, content: str) -> None:
        # self.console.print(content, end="", markup=False)
        # store for markdown rendering later
        self._assistant_buffer += content

        # stream raw tokens for live feedback
        # self.console.print(content, end="", markup=False, highlight=False)

    def render_assistant_message(self, content: str):
        lines = content.split("\n")
        blocks = []

        code_block = []
        in_code = False
        lang = "python"

        for line in lines:

            # detect ``` blocks
            if line.strip().startswith("```"):
                if not in_code:
                    in_code = True
                    lang = line.strip().replace("```", "") or "python"
                    code_block = []
                else:
                    blocks.append(
                        Syntax(
                            "\n".join(code_block),
                            lang,
                            theme="monokai",
                            word_wrap=True
                        )
                    )
                    in_code = False
                continue

            if in_code:
                code_block.append(line)
                continue

            # bold text (** **)
            bold_match = re.findall(r"\*\*(.*?)\*\*", line)
            if bold_match:
                text = Text(line.replace("**", ""), style="#ff8c42")
                blocks.append(text)
                continue

            # bullet points
            if line.strip().startswith(("-", "*", "•")):
                bullet = Text("• ", style="muted")
                bullet.append(line.strip()[1:].strip())
                blocks.append(bullet)
                continue

            # normal paragraph
            blocks.append(Text(line))

        return Group(*blocks)

    def ordered_arguments(self, tool_name, args: dict[str, Any]) -> list[tuple]:
        # tuple is chosen because it is ordered and immutable
        PREFERRED_ORDER = {
            "read_file": ["path", "offset", "limit"],
            "write_file": ["path", "create_directories", "content"],
            "edit_file": ["path", "replace_all", "old_string", "new_string"],
            "shell": ["command", "timeout", "cwd"],
            "list_dir": ["path", "include_hidden"],
            "grep": ["path", "case_insensitive", "pattern"],
            "glob": ["path", "pattern"],
            "todos": ["id", "action", "content"],
            "memory": ["action", "key", "value"]
        }
        preferred = PREFERRED_ORDER.get(tool_name, [])
        ordered: list[tuple[str, Any]] = []
        seen = set()

        for key in preferred:
            if key in args:
                ordered.append((key, args[key]))
                seen.add(key)
        # (path,offset,offset2) - (path,offset) to get offset2 incase the LLM hallucinates and gets different paths
        remaining_keys = set(args.keys()-seen)
        ordered.extend(((key, args[key]) for key in remaining_keys))

        return ordered

    def render_arguments_table(self, tool_name: str, arguments: dict[str, Any]) -> Table:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="muted", justify="right", no_wrap=True)
        table.add_column(style="code", overflow="fold")

        for key, value in self.ordered_arguments(tool_name, arguments):
            # Convert values into renderable text
            if isinstance(value, str):
                if key in ("content", "old_string", "new_string"):
                    line_count = len(value.splitlines()) or 0
                    byte_count = len(value.encode('utf-8', errors="replace"))
                    value = f"<{line_count} lines . {byte_count} bytes>"

                if isinstance(value, bool):
                    value = str(value)
            table.add_row(str(key), Text(str(value), style="code"))

        return table

        # path   main.py
        # offset 1
        # limit  None
        # for this look in table format

    def tool_call_start(self, call_id: str, name: str, tool_kind: str | None, arguments: dict[str, Any]):
        self._tool_args_by_call_id[call_id] = arguments

        border_style = f"tool.{tool_kind}" if tool_kind else "tool"

        title = Text.assemble(
            ("⏺ ", "muted"),
            (name, "tool"),
            ("  ", "muted"),
            (f"#{call_id[:8]}", "muted")
        )

        # just to display the path in a relative or an absolute way
        display_args = dict(arguments)
        for key in ("path", "cwd"):
            val = display_args.get(key)  # main.py
            if isinstance(val, str) and self.cwd:
                display_args[key] = str(display_path_rel_to_cwd(Path(val), self.cwd))

        # for a bordered box around everything
        panel = Panel(
            self.render_arguments_table(name, arguments) if display_args else Text(
                "(no args)", style="muted"),
            title=title,
            title_align="left",
            subtitle=Text("running", style="muted"),
            subtitle_align="right",
            box=box.ROUNDED,
            border_style=border_style,
            padding=(1, 2)
        )
        self.console.print()
        self.console.print(panel)

    # tuple is for ordered integer and code line
    def extract_read_file_code(self, text: str) -> tuple[int, str] | None:
        body = text
        header_match = re.match(r"^Showing lines (\d+)-(\d+) of (\d+)\n\n", text)

        # stripping body to contain content after header
        if header_match:
            body = text[header_match.end():]

        code_lines: list[str] = []
        start_line: int | None = None

        for line in body.splitlines():
            # 1 | def main() (eg), remember that indentation matters too
            m = re.match(r"^\s*(\d+)\|(.*)$", line)
            if not m:
                return None
            line_no = int(m.group(1))
            if start_line is None:
                start_line = line_no
            code_lines.append(m.group(2))

        if start_line is None:
            return None

        return start_line, "\n".join(code_lines)

    def guess_language(self, path: str | None) -> str:
        if not path:
            return "text"
        suffix = Path(path).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "jsx",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".json": "json",
            ".toml": "toml",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".kt": "kotlin",
            ".swift": "swift",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".css": "css",
            ".html": "html",
            ".xml": "xml",
            ".sql": "sql",
        }.get(suffix, "text")

    def print_welcome(self, title: str, lines: list[str]) -> None:
        body = "\n".join(lines)
        self.console.print(
            Panel(
                Text(body, style="code"),
                title=Text(title, style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2)
            )
        )

    def tool_call_complete(self,
                           call_id: str,
                           name: str,
                           tool_kind: str | None,
                           success: bool, output: str,
                           error: str | None,
                           metadata: dict[str, Any] | None,
                           diff: str | None,
                           truncated: bool,
                           exit_code: int | None):

        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        status_icon = "✓" if success else "✗"
        status_style = "success" if success else "error"
        title = Text.assemble(
            (f"{status_icon}", status_style),
            (name, "tool"),
            ("  ", "muted"),
            (f"#{call_id[:8]}", "muted")
        )

        args = self._tool_args_by_call_id.get(call_id, {})

        primary_path = None
        blocks = []
        if isinstance(metadata, dict) and isinstance(metadata.get("path"), str):
            primary_path = metadata.get("path")

        if name == "read_file" and success:
            if primary_path:
                result = self.extract_read_file_code(output)
                if result is None:
                    start_line, code = None, None
                else:
                    start_line, code = result
                shown_start = 0
                shown_end = 0
                total_lines = 0
                programming_language = ""

                if metadata:
                    shown_start = metadata.get("shown_start", 0)
                    shown_end = metadata.get("shown_end", 0)
                    total_lines = metadata.get("total_lines", 0)
                    programming_language = self.guess_language(primary_path)

                blocks.append(Text())

                header_parts = [display_path_rel_to_cwd(primary_path, self.cwd)]
                header_parts.append(" ⏺ ")

                if shown_start and shown_end and total_lines:
                    header_parts.append(f"lines {shown_start}-{shown_end} of {total_lines}")

                header = "".join(header_parts)
                blocks.append(Text(header, style="muted"))
                blocks.append(
                    Syntax(
                        code=code or "",
                        lexer=programming_language,
                        theme="monokai",
                        line_numbers=True,
                        start_line=start_line or 0,
                        word_wrap=True
                    )
                )
            else:
                truncate_text(output, "", 240)
                blocks.append(Syntax(output, "text", theme="monokai", word_wrap=False))

        elif name in {"write_file", "edit_file"} and success and diff:
            output_line = output.strip() if output.strip() else "Completed"
            blocks.append(Text(output_line, style="muted"))
            diff_text = diff
            diff_display = truncate_text(diff_text, "openrouter/free", 240)

            blocks.append(Syntax(diff_display, 'diff', theme="monokai", word_wrap=True))

            # just to display the path in a relative or an absolute way

        elif name == "shell" and success:
            command = args.get("command")
            if isinstance(command, str) and command.strip():
                blocks.append(Text(f'$ {command.strip()}', style="muted"))

            if exit_code is not None:
                blocks.append(Text(f"exit_code={exit_code}", style="muted"))

            output_display = truncate_text(output, "openrouter/free", 2400)

            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True
                )
            )

        elif name == "list_dir":
            entries = args.get("entries")
            path = args.get("path")
            recursive = args.get("recursive")
            max_depth = args.get("max_depth")

            summary = []

            if isinstance(path, str):
                summary.append(path)

            if isinstance(entries, int):
                summary.append(f"{entries} entries")

            if recursive:
                if isinstance(max_depth, int):
                    summary.append(f"recursive (depth={max_depth})")
                else:
                    summary.append("recursive")

            if summary:
                blocks.append(Text(" . ".join(summary), style="muted"))

            output_display = truncate_text(
                output,
                "openrouter/free",
                2400
            )

            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True
                )
            )

            if error and not success:
                blocks.append(Text(error, style="error"))

                output_display = truncate_text(output, "openrouter/free", 2400)

                if output_display.strip():
                    blocks.append(Syntax(
                        output_display,
                        "text",
                        theme="monokai",
                        word_wrap=True))

                else:
                    blocks.append(Text("(no output)", style="muted"))

        elif name == "grep" and success:
            matches = args.get("matches")
            files_searched = args.get("files_searched")
            summary = []

            if isinstance(matches, int):
                summary.append(f"{matches} matches found")
            if isinstance(files_searched, int):
                summary.append(f"{files_searched} files searched")

            if summary:
                blocks.append(Text(" . ".join(summary), style="muted"))

            output_display = truncate_text(output,
                                           "openrouter/free",
                                           2400)

            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True
                )
            )

        elif name == "grep" and success:
            matches = args.get("matches")

            if isinstance(matches, int):
                blocks.append(Text(f"{matches} files found", style="muted"))

            output_display = truncate_text(output,
                                           "openrouter/free",
                                           2400)

            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True
                )
            )

        if truncated:
            blocks.append(Text("note: tool output was truncated", style="warning"))

        if not blocks:
            if output.strip():
                blocks.append(
                    Syntax(
                        truncate_text(output, "", 2400),
                        "text",
                        theme="monokai",
                        word_wrap=True
                    )
                )
            else:
                blocks.append(Text("(no output)", style="muted"))

        elif name == "web_search" and success:
            results = args.get("results")
            query = args.get("query")
            summary = []
            if isinstance(query, str):
                summary.append(query)
            if isinstance(results, int):
                summary.append(f"{results} results")

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))

            output_display = truncate_text(
                output,
                "openrouter/free",
                2400
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )

        elif name == "web_fetch" and success:
            status_code = args.get("status_code")
            content_length = args.get("content_length")
            url = args.get("url")
            summary = []
            if isinstance(status_code, str):
                summary.append(str(status_code))
            if isinstance(content_length, int):
                summary.append(f"{content_length} bytes")
            if isinstance(url, str):
                summary.append(url)

            if summary:
                blocks.append(Text(" • ".join(summary), style="muted"))

            output_display = truncate_text(
                output,
                "openrouter/free",
                2400
            )
            blocks.append(
                Syntax(
                    output_display,
                    "text",
                    theme="monokai",
                    word_wrap=True,
                )
            )

        elif name == "todos" and success:
            todos = {}
            groups = {}
            if metadata and metadata.get("type") == "todos":
                todos = metadata.get("todos", {})

            if not todos:
                blocks.append(Text("No todos", style="bold yellow"))
            else:
                groups = {
                    "pending": [],
                    "in_progress": [],
                    "completed": []
                }

                for tid, t in todos.items():
                    groups[t["status"]].append((tid, t))

                for status, items in groups.items():
                    if not items:
                        continue

                    if status == "pending":
                        color = "yellow"
                        icon = "⏳"
                    elif status == "in_progress":
                        color = "cyan"
                        icon = "🔄"
                    else:
                        color = "green"
                        icon = "✔"

                    blocks.append(Text(f"{icon} {status.upper()}", style=f"bold {color}"))

                    table = Table(
                        show_header=True,
                        header_style="bold magenta",
                        border_style=color,
                        box=box.ROUNDED
                    )
                    table.add_column("ID", style="dim", width=10)
                    table.add_column("Priority", justify="center")
                    table.add_column("Task", overflow="fold")

                    for tid, t in items:
                        priority = t["priority"]
                        if priority == "high":
                            p_text = Text(priority, style="bold red")
                        elif priority == "medium":
                            p_text = Text(priority, style="yellow")
                        else:
                            p_text = Text(priority, style="green")

                        table.add_row(
                            tid,
                            p_text,
                            t["content"]
                        )

                    blocks.append(table)

        elif name == "memory" and success:
            action = args.get('action')
            key = args.get('key')
            found = args.get("found")

            summary = []

            if isinstance(action, str) and action:
                summary.append(action)
            if isinstance(key, str) and key:
                summary.append(key)
            if isinstance(found, bool) and found is not None:
                summary.append("found" if found else "missing")

            if summary:
                blocks.append(Text(".".join(summary), style="muted"))

        elif name.startswith("subagent_"):

            agent_name = args.get("agent", "unknown")
            termination = args.get("termination", "")
            tools_used = args.get("tools_used", [])
            error_msg = args.get("error")

            # Header
            blocks.append(
                Panel(
                    f"🤖 {agent_name}\n"
                    f"Termination: {termination}\n"
                    f"Tools: {', '.join(tools_used) if tools_used else 'None'}",
                    style="cyan",
                    title="Sub-Agent"
                )
            )
            if not success:
                blocks.append(
                    Panel(
                        error_msg or output,
                        title="❌ Error",
                        border_style="red"
                    )
                )
            else:
                blocks.append(
                    Panel(
                        Markdown(output),
                        title="📄 Result",
                        border_style="green"
                    )
                )

        else:
            # fallback if no tool call is executed or for subagents
            if error and not success:
                blocks.append(Text(error, style='error'))

            output_display = truncate_text(
                output,
                "openrouter/free",
                2400
            )
            if output_display.strip():
                blocks.append(
                    Syntax(
                        output_display,
                        "text",
                        theme="monokai",
                        word_wrap=True,
                    )
                )
            else:
                blocks.append(Text("(no output)", style="muted"))

        # for a bordered box around everything
        panel = Panel(
            Group(*blocks),
            title=title,
            title_align="left",
            subtitle=Text("done" if success else "failed", style=status_style),
            subtitle_align="right",
            box=box.ROUNDED,
            border_style=border_style,
            padding=(1, 2)
        )
        self.console.print()
        self.console.print(panel)
