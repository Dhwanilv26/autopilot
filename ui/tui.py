from pathlib import Path
from typing import Any, List

from click import prompt
from rich.console import Console, RenderableType
from rich.theme import Theme
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.syntax import Syntax
from rich.prompt import Prompt
from rich.console import Group
from rich.markdown import Markdown
from rich.padding import Padding
import re

from config import config
from tools.base import ToolConfirmation
from utils.markdown import normalize_markdown_assistant, normalize_markdown_subagent
from utils.paths import display_path_rel_to_cwd
from utils.text import truncate_text
from config.config import Config


AGENT_THEME = Theme(
    {
        # Core status
        "info":            "#ff8c42",
        "warning":         "orange1",
        "error":           "bright_red bold",
        "success":         "spring_green3",
        "dim":             "grey37",
        "muted":           "grey46",
        "border":          "grey27",
        "highlight":       "underline bold #ff8c42",

        # Roles
        "user":            "deep_sky_blue1 bold",
        "assistant":       "bold #ff8c42",
        "assistant.text":  "#ff8c42",

        # Rich Markdown overrides
        "markdown.heading":     "bold #ff8c42",
        "markdown.bold":        "bold #ff8c42",
        "markdown.code":        "#ff8c42",
        "markdown.item":        "white",
        "markdown.block_quote": "dim italic",
        "markdown.hr":          "grey37",

        # Inline code / syntax text
        "code": "grey93",

        # Tool-kind accent colours
        "tool":         "medium_purple1 bold",
        "tool.read":    "aquamarine1",
        "tool.write":   "gold1",
        "tool.shell":   "bright_magenta",
        "tool.network": "cornflower_blue",
        "tool.memory":  "sea_green1",
        "tool.mcp":     "cyan2",

        # Status chip labels
        "chip.running": "grey46",
        "chip.done":    "spring_green3",
        "chip.failed":  "bright_red",
    }
)


TOOL_ICONS: dict[str, str] = {
    "read_file":  "📖",
    "write_file": "✏️",
    "edit_file":  "📝",
    "shell":      "🖥️",
    "list_dir":   "📂",
    "grep":       "🔍",
    "glob":       "🌐",
    "web_search": "🌐",
    "web_fetch":  "🌍",
    "todos":      "✅",
    "memory":     "🧠",
}

_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(
            theme=AGENT_THEME,
            highlight=True,
            markup=True,
            soft_wrap=True,
            force_terminal=True,
        )
    return _console


def _tool_icon(name: str) -> str:
    if name.startswith("subagent_"):
        return "🤖"
    return TOOL_ICONS.get(name, "⚙️")


def _fmt_bytes(n: int) -> str:
    """Human-readable byte size."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.1f} MB"


class TUI:

    def __init__(self, config: Config, console: Console | None = None, ) -> None:
        self.console = console or get_console()
        self._assistant_stream_open = False
        self._assistant_buffer: str = ""
        # Cached args per call_id; needed in tool_call_complete
        self._tool_args_by_call_id: dict[str, dict[str, Any]] = {}
        self.cwd = Path.cwd()
        self.config = config

    # ── Assistant ─────────────────────────────────────────────────────────────

    def begin_assistant(self) -> None:
        self.console.print()
        self._assistant_stream_open = True
        self._assistant_buffer = ""

    def end_assistant(self) -> None:
        if not self._assistant_stream_open:
            return

        cleaned = normalize_markdown_assistant(self._assistant_buffer)
        md = Markdown(cleaned, code_theme="monokai")

        title = Text.assemble(("◆ ", "assistant"), ("Assistant", "assistant"))

        panel = Panel(
            md,
            title=title,
            title_align="left",
            border_style="success",
            box=box.ROUNDED,
            padding=(1, 2),
            expand=True,
        )

        self.console.print()
        self.console.print(panel)
        self.console.print()

        self._assistant_stream_open = False
        self._assistant_buffer = ""

    def stream_assistant_delta(self, content: str) -> None:
        """Buffer streamed tokens; rendered all at once in end_assistant."""
        self._assistant_buffer += content

    def render_assistant_message(self, content: str) -> Group:
        """
        Block-by-block renderer for assistant content used when
        streaming is bypassed entirely.
        """
        lines = content.split("\n")
        blocks: list[Any] = []
        code_block: list[str] = []
        in_code = False
        lang = "python"

        for line in lines:
            if line.strip().startswith("```"):
                if not in_code:
                    in_code = True
                    lang = line.strip().lstrip("`").strip() or "python"
                    code_block = []
                else:
                    blocks.append(
                        Syntax("\n".join(code_block), lang, theme="monokai", word_wrap=True)
                    )
                    in_code = False
                continue

            if in_code:
                code_block.append(line)
                continue

            if re.search(r"\*\*(.*?)\*\*", line):
                blocks.append(Text(line.replace("**", ""), style="#ff8c42"))
                continue

            if line.strip().startswith(("-", "*", "•")):
                t = Text("  • ", style="muted")
                t.append(line.strip()[1:].strip(), style="white")
                blocks.append(t)
                continue

            blocks.append(Text(line))

        return Group(*blocks)

    # ── Argument ordering ─────────────────────────────────────────────────────

    _PREFERRED_ORDER: dict[str, list[str]] = {
        "read_file":  ["path", "offset", "limit"],
        "write_file": ["path", "create_directories", "content"],
        "edit_file":  ["path", "replace_all", "old_string", "new_string"],
        "shell":      ["command", "timeout", "cwd"],
        "list_dir":   ["path", "include_hidden"],
        "grep":       ["path", "case_insensitive", "pattern"],
        "glob":       ["path", "pattern"],
        "todos":      ["id", "action", "content"],
        "memory":     ["action", "key", "value"],
    }

    def ordered_arguments(self, tool_name: str, args: dict[str, Any]) -> list[tuple]:
        preferred = self._PREFERRED_ORDER.get(tool_name, [])
        ordered: list[tuple[str, Any]] = []
        seen: set[str] = set()

        for key in preferred:
            if key in args:
                ordered.append((key, args[key]))
                seen.add(key)

        for key in args.keys() - seen:
            ordered.append((key, args[key]))

        return ordered

    def render_arguments_table(self, tool_name: str, arguments: dict[str, Any]) -> Table:
        """
        Compact two-column grid: key (right-aligned muted) | value (code style).
        Large content fields are summarised as <N lines · M bytes>.
        """
        table = Table.grid(padding=(0, 2))
        table.add_column(style="muted", justify="right", no_wrap=True)
        table.add_column(style="code", overflow="fold")

        for key, value in self.ordered_arguments(tool_name, arguments):
            if isinstance(value, str) and key in ("content", "old_string", "new_string"):
                lines = len(value.splitlines()) or 0
                bsize = len(value.encode("utf-8", errors="replace"))
                value = f"<{lines} lines · {bsize} bytes>"
            if isinstance(value, bool):
                value = str(value).lower()

            table.add_row(key, Text(str(value), style="code"))

        return table

    # ── Tool call start ───────────────────────────────────────────────────────

    def tool_call_start(
        self,
        call_id: str,
        name: str,
        tool_kind: str | None,
        arguments: dict[str, Any],
    ) -> None:
        self._tool_args_by_call_id[call_id] = arguments

        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        icon = _tool_icon(name)

        title = Text.assemble(
            (f"{icon} ", "muted"),
            (name, "tool"),
            ("  ", ""),
            (f"#{call_id[:8]}", "dim"),
        )

        # Relativise path / cwd for display only (don't mutate the stored args)
        display_args = dict(arguments)
        for key in ("path", "cwd"):
            val = display_args.get(key)
            if isinstance(val, str) and self.cwd:
                display_args[key] = str(display_path_rel_to_cwd(Path(val), self.cwd))

        body = (
            self.render_arguments_table(name, display_args)
            if display_args
            else Text("(no arguments)", style="muted")
        )

        panel = Panel(
            body,
            title=title,
            title_align="left",
            subtitle=Text(" running ", style="chip.running"),
            subtitle_align="right",
            box=box.ROUNDED,
            border_style=border_style,
            padding=(0, 2),
        )

        self.console.print()
        self.console.print(panel)

    # ── File code extraction ──────────────────────────────────────────────────

    def extract_read_file_code(self, text: str) -> tuple[int, str] | None:
        """
        Parse the numbered-line format returned by read_file:
            1| def main():
            2|     pass
        Returns (start_line, code_string) or None if format doesn't match.
        """
        body = text
        header = re.match(r"^Showing lines (\d+)-(\d+) of (\d+)\n\n", text)
        if header:
            body = text[header.end():]

        code_lines: list[str] = []
        start_line: int | None = None

        for line in body.splitlines():
            m = re.match(r"^\s*(\d+)\|(.*)$", line)
            if not m:
                return None
            lno = int(m.group(1))
            if start_line is None:
                start_line = lno
            code_lines.append(m.group(2))

        if start_line is None:
            return None

        return start_line, "\n".join(code_lines)

    def guess_language(self, path: str | None) -> str:
        if not path:
            return "text"
        return {
            ".py":    "python",
            ".js":    "javascript",
            ".jsx":   "jsx",
            ".ts":    "typescript",
            ".tsx":   "tsx",
            ".json":  "json",
            ".toml":  "toml",
            ".yaml":  "yaml",
            ".yml":   "yaml",
            ".md":    "markdown",
            ".sh":    "bash",
            ".bash":  "bash",
            ".zsh":   "bash",
            ".rs":    "rust",
            ".go":    "go",
            ".java":  "java",
            ".kt":    "kotlin",
            ".swift": "swift",
            ".c":     "c",
            ".h":     "c",
            ".cpp":   "cpp",
            ".hpp":   "cpp",
            ".css":   "css",
            ".html":  "html",
            ".xml":   "xml",
            ".sql":   "sql",
        }.get(Path(path).suffix.lower(), "text")

    # ── Welcome banner ────────────────────────────────────────────────────────

    def print_welcome(self, title: str, lines: list[str]) -> None:
        body = "\n".join(lines)
        self.console.print(
            Panel(
                Text(body, style="code"),
                title=Text(title, style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    # ── Shared block helpers ──────────────────────────────────────────────────

    def _summary_line(self, parts: list[str], style: str = "muted") -> Text:
        """Join non-empty strings with a dim separator into a single Text."""
        t = Text(style=style)
        non_empty = [p for p in parts if p]
        for i, part in enumerate(non_empty):
            t.append(part)
            if i < len(non_empty) - 1:
                t.append("  ·  ", style="dim")
        return t

    def _syntax_block(self, content: str, language: str = "text") -> Syntax:
        return Syntax(content, language, theme="monokai", word_wrap=True)

    def _truncated_syntax(
        self,
        output: str,
        language: str = "text",
        limit: int = 2400,
        model: str | None = None
    ) -> Syntax:
        model = self.config.model_name
        return self._syntax_block(truncate_text(output, model or "openrouter/free", limit), language)

    # ── Tool call complete ────────────────────────────────────────────────────

    def tool_call_complete(
        self,
        call_id: str,
        name: str,
        tool_kind: str | None,
        success: bool,
        output: str,
        error: str | None,
        metadata: dict[str, Any] | None,
        diff: str | None,
        truncated: bool,
        exit_code: int | None,
    ) -> None:

        border_style = f"tool.{tool_kind}" if tool_kind else "tool"
        status_icon = "✓" if success else "✗"
        status_style = "chip.done" if success else "chip.failed"
        icon = _tool_icon(name)

        title = Text.assemble(
            (f"{status_icon} ", status_style),
            (f"{icon} ", "muted"),
            (name, "tool"),
            ("  ", ""),
            (f"#{call_id[:8]}", "dim"),
        )

        args = self._tool_args_by_call_id.get(call_id, {})
        meta = metadata or {}  # safe: metadata may be None

        # primary_path is the actual path operated on (from metadata)
        primary_path: str | None = meta.get("path") if isinstance(meta.get("path"), str) else None

        blocks: list[Any] = []

        # ── read_file ─────────────────────────────────────────────────────────
        if name == "read_file" and success:
            if primary_path:
                result = self.extract_read_file_code(output)
                start_line, code = result if result else (None, None)

                shown_start = meta.get("shown_start", 0)
                shown_end = meta.get("shown_end", 0)
                total_lines = meta.get("total_lines", 0)
                lang = self.guess_language(primary_path)
                rel_path = display_path_rel_to_cwd(Path(primary_path), self.cwd)

                header = Text()
                header.append(str(rel_path), style="bold aquamarine1")
                if shown_start and shown_end and total_lines:
                    header.append(f"  lines {shown_start}–{shown_end}", style="muted")
                    header.append(f" of {total_lines}", style="dim")

                blocks.append(header)
                blocks.append(
                    Syntax(
                        code=code or "",
                        lexer=lang,
                        theme="monokai",
                        line_numbers=True,
                        start_line=start_line or 1,
                        word_wrap=True,
                    )
                )
            else:
                blocks.append(self._truncated_syntax(output))

        # ── write_file / edit_file ────────────────────────────────────────────
        elif name in {"write_file", "edit_file"} and success:
            msg = output.strip() or "Completed"
            path_str = meta.get("path", "")

            if path_str:
                t = Text()
                t.append(str(display_path_rel_to_cwd(Path(path_str), self.cwd)), style="bold gold1")
                t.append(f"  {msg}", style="muted")
                blocks.append(t)
            else:
                blocks.append(Text(msg, style="muted"))

            if diff:
                blocks.append(self._syntax_block(truncate_text(
                    diff, str(self.config.model_name), 2400), "diff"))

        # ── shell ─────────────────────────────────────────────────────────────
        elif name == "shell":
            command = args.get("command", "")
            if isinstance(command, str) and command.strip():
                cmd_text = Text()
                cmd_text.append("$ ", style="bright_magenta bold")
                cmd_text.append(command.strip(), style="code")
                blocks.append(cmd_text)

            if exit_code is not None:
                ec_style = "success" if exit_code == 0 else "error"
                ec_text = Text()
                ec_text.append("exit ", style="dim")
                ec_text.append(str(exit_code), style=ec_style)
                blocks.append(ec_text)

            if not success and error:
                blocks.append(Text(error, style="error"))

            if output.strip():
                blocks.append(self._truncated_syntax(output))

        # ── list_dir ──────────────────────────────────────────────────────────
        elif name == "list_dir":
            path = args.get("path", "")
            recursive = args.get("recursive")
            max_depth = args.get("max_depth")
            entries = meta.get("entries")   # result → metadata

            parts: list[str] = []
            if path:
                parts.append(str(display_path_rel_to_cwd(Path(path), self.cwd)))
            if isinstance(entries, int):
                parts.append(f"{entries} entries")
            if recursive:
                parts.append(
                    f"recursive (depth={max_depth})" if isinstance(max_depth, int) else "recursive"
                )

            if parts:
                blocks.append(self._summary_line(parts))

            if not success and error:
                blocks.append(Text(error, style="error"))

            if output.strip():
                blocks.append(self._truncated_syntax(output))
            elif not blocks:
                blocks.append(Text("(no output)", style="muted"))

        # ── grep ──────────────────────────────────────────────────────────────
        elif name == "grep":
            matches = meta.get("matches")        # result → metadata
            files_searched = meta.get("files_searched")  # result → metadata
            pattern = args.get("pattern", "")
            path = args.get("path", "")

            parts = []
            if pattern:
                parts.append(f"/{pattern}/")
            if path:
                parts.append(str(display_path_rel_to_cwd(Path(path), self.cwd)))
            if isinstance(matches, int):
                parts.append(f"{matches} match{'es' if matches != 1 else ''}")
            if isinstance(files_searched, int):
                parts.append(f"{files_searched} files")

            if parts:
                blocks.append(self._summary_line(parts))

            if success and output.strip():
                blocks.append(self._truncated_syntax(output))
            elif not success and error:
                blocks.append(Text(error, style="error"))

        # ── web_search ────────────────────────────────────────────────────────
        elif name == "web_search":
            query = args.get("query", "")  # input  → args
            results = meta.get("results")    # result → metadata

            parts = []
            if query:
                parts.append(f'"{query}"')
            if isinstance(results, int):
                parts.append(f"{results} results")

            if parts:
                blocks.append(self._summary_line(parts))

            if output.strip():
                blocks.append(self._truncated_syntax(output))
            elif not success and error:
                blocks.append(Text(error, style="error"))

        # ── web_fetch ─────────────────────────────────────────────────────────
        elif name == "web_fetch":
            url = args.get("url", "")        # input  → args
            status_code = meta.get("status_code")    # result → metadata
            content_length = meta.get("content_length")  # result → metadata

            summary = Text()
            if url:
                summary.append(url, style="muted")
            if status_code is not None:
                sc_str = str(status_code)
                sc_style = "success" if sc_str.startswith("2") else "error"
                summary.append("  ·  ", style="dim")
                summary.append(sc_str, style=sc_style)
            if isinstance(content_length, int):
                summary.append("  ·  ", style="dim")
                summary.append(_fmt_bytes(content_length), style="muted")

            if summary.plain:
                blocks.append(summary)

            if output.strip():
                blocks.append(self._truncated_syntax(output))
            elif not success and error:
                blocks.append(Text(error, style="error"))

        # ── todos ─────────────────────────────────────────────────────────────
        elif name == "todos" and success:
            todos: dict = {}
            if meta.get("type") == "todos":
                todos = meta.get("todos", {})

            if not todos:
                blocks.append(Text("  No todos found.", style="muted italic"))
            else:
                groups: dict[str, list] = {
                    "pending":     [],
                    "in_progress": [],
                    "completed":   [],
                }
                for tid, t in todos.items():
                    groups[t["status"]].append((tid, t))

                STATUS_CONFIG = {
                    "pending":     ("⏳", "yellow",         "Pending"),
                    "in_progress": ("🔄", "cornflower_blue", "In Progress"),
                    "completed":   ("✔",  "spring_green3",  "Completed"),
                }
                PRIORITY_STYLES = {
                    "high":   ("●", "bright_red"),
                    "medium": ("●", "yellow"),
                    "low":    ("●", "spring_green3"),
                }

                for status, (s_icon, color, label) in STATUS_CONFIG.items():
                    items = groups[status]
                    if not items:
                        continue

                    section_title = Text()
                    section_title.append(f"{s_icon} ", style=color)
                    section_title.append(label, style=f"bold {color}")
                    blocks.append(Padding(section_title, (1, 0, 0, 0)))

                    tbl = Table(
                        show_header=True,
                        header_style=f"bold {color}",
                        border_style="dim",
                        box=box.SIMPLE_HEAD,
                        padding=(0, 1),
                    )
                    tbl.add_column("ID",       style="dim",  no_wrap=True, width=12)
                    tbl.add_column("Priority", justify="center", width=10)
                    tbl.add_column("Task",     overflow="fold")

                    for tid, t in items:
                        prio = t.get("priority", "low")
                        dot, p_style = PRIORITY_STYLES.get(prio, ("●", "muted"))
                        p_text = Text()
                        p_text.append(f"{dot} ", style=p_style)
                        p_text.append(prio, style=p_style)
                        tbl.add_row(tid, p_text, t.get("content", ""))

                    blocks.append(tbl)

        # ── memory ────────────────────────────────────────────────────────────
        elif name == "memory" and success:
            action = args.get("action", "")
            key = args.get("key", "")
            found = meta.get("found")  # result → metadata

            parts = []
            if action:
                parts.append(action)
            if key:
                parts.append(key)
            if isinstance(found, bool):
                parts.append("found" if found else "not found")

            if parts:
                blocks.append(self._summary_line(parts))

            if output.strip():
                blocks.append(self._truncated_syntax(output))

        # ── subagent_* ────────────────────────────────────────────────────────
        elif name.startswith("subagent_"):
            agent_name = meta.get("agent", "unknown")
            termination = meta.get("termination", "—")
            tools_used = meta.get("tools_used", [])
            error_msg = meta.get("error")

            clean_output = normalize_markdown_subagent(output)

            # Compact info line — no nested panel, keeps visual nesting shallow
            info = Text()
            info.append("agent  ", style="dim")
            info.append(str(agent_name), style="bold cyan")
            info.append("   term  ", style="dim")
            info.append(str(termination), style="muted")
            if tools_used:
                info.append("   tools  ", style="dim")
                info.append(", ".join(tools_used), style="muted")
            blocks.append(info)
            blocks.append(Text())  # blank spacer

            if not success:
                blocks.append(
                    Panel(
                        Text(error_msg or output, style="error"),
                        title="Error",
                        border_style="bright_red",
                        box=box.ROUNDED,
                        padding=(0, 1),
                    )
                )
            else:
                blocks.append(
                    Panel(
                        Markdown(clean_output, code_theme="monokai"),
                        title="Result",
                        border_style="spring_green3",
                        box=box.ROUNDED,
                        padding=(1, 2),
                    )
                )

        # ── fallback ──────────────────────────────────────────────────────────
        else:
            if not success and error:
                blocks.append(Text(error, style="error"))

            if output.strip():
                blocks.append(self._truncated_syntax(output))
            else:
                blocks.append(Text("(no output)", style="muted"))

        # ── Truncation notice (always appended last) ──────────────────────────
        if truncated:
            trunc = Text()
            trunc.append("⚠ ", style="warning")
            trunc.append("output was truncated", style="muted italic")
            blocks.append(trunc)

        # ── Empty guard ───────────────────────────────────────────────────────
        if not blocks:
            blocks.append(Text("(no output)", style="muted"))

        # ── Completion panel ──────────────────────────────────────────────────
        subtitle = Text()
        subtitle.append(f" {'done' if success else 'failed'} ", style=status_style)

        panel = Panel(
            Group(*blocks),
            title=title,
            title_align="left",
            subtitle=subtitle,
            subtitle_align="right",
            box=box.ROUNDED,
            border_style=border_style,
            padding=(1, 2),
        )

        self.console.print()
        self.console.print(panel)

    async def handle_confirmation(self, confirmation: ToolConfirmation) -> bool:
        output: List[RenderableType] = []

        # 🔹 Tool name
        output.append(
            Text(f"🔧 {confirmation.tool_name}", style="bold cyan")
        )

        # 🔹 Description
        output.append(
            Text(confirmation.description, style="white")
        )

        # 🔹 Command (if exists)
        if confirmation.command:
            output.append(
                Panel(
                    Text(f"$ {confirmation.command}", style="bold yellow"),
                    border_style="yellow",
                    title="Command",
                    box=box.MINIMAL
                )
            )

        # 🔹 Diff (if exists)
        if confirmation.diff:
            diff_text = confirmation.diff.to_diff()

            output.append(
                Panel(
                    Syntax(
                        diff_text,
                        "diff",
                        theme="monokai",
                        word_wrap=True
                    ),
                    border_style="magenta",
                    title="Changes",
                    box=box.MINIMAL
                )
            )

        # 🔹 Print UI
        self.console.print()
        self.console.print(
            Panel(
                Group(*output),
                title="⚠ Approval Required",
                border_style="bright_yellow",
                box=box.ROUNDED,
                padding=(1, 2)
            )
        )

        # 🔹 Ask user
        choice = Prompt.ask(
            "[bold yellow]Approve this action?[/bold yellow]",
            choices=["y", "n", "yes", "no"],
            default="n"
        )

        return choice.lower() in {"y", "yes"}

    def show_help(self) -> None:
        help_text = """
## Commands

- `/help` — Display this help menu  
- `/exit` or `/quit` — Exit the agent  
- `/clear` — Clear conversation history  
- `/config` — View current configuration  
- `/model <name>` — Switch model  
- `/approval <mode>` — Set approval mode  
- `/stats` — View session statistics  
- `/tools` — List available tools  
- `/mcp` — Check MCP server status  
- `/save` — Save current session  
- `/checkpoint [name]` — Create a checkpoint  
- `/checkpoints` — List all checkpoints  
- `/restore <checkpoint_id>` — Restore a checkpoint  
- `/sessions` — List saved sessions  
- `/resume <session_id>` — Resume a session  

## Tips

- Type naturally to chat with the agent  
- The agent can read, write, and execute code  
- Some actions may require approval (configurable)  
"""
        self.console.print(Markdown(help_text))
