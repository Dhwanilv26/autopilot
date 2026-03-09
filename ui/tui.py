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
                           soft_wrap=True)

    return _console


class TUI:
    def __init__(self, console: Console | None = None) -> None:
        self.console = _console or get_console()
        self._assistant_stream_open = False
        self._assistant_buffer: str = ""
        # call id and all args for that tool, used for caching as they are needed in multiple event displays in the tui
        self._tool_args_by_call_id: dict[str, dict[str, Any]] = {}
        self.cwd = Path.cwd()

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
            "read_file": ["path", "offset", "limit"]
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
                           truncated: bool):

        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        status_icon = "✓" if success else "✗"
        status_style = "success" if success else "error"
        title = Text.assemble(
            (f"{status_icon}", status_style),
            (name, "tool"),
            ("  ", "muted"),
            (f"#{call_id[:8]}", "muted")
        )

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

        # just to display the path in a relative or an absolute way

        if truncated:
            blocks.append(Text("note: tool output was truncated", style="warning"))

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
