from pathlib import Path
from typing import Any, Tuple

from rich.console import Console
from rich.theme import Theme
from rich.rule import Rule
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box

from utils.paths import resolve_path
AGENT_THEME = Theme(
    {
        # General - Using a mix of professional and alert neons
        "info": "dodger_blue1",
        "warning": "orange1",
        "error": "bright_red bold",
        "success": "spring_green3",
        "dim": "grey37",
        "muted": "grey42",
        "border": "grey27",
        "highlight": "underline bold sky_blue1",

        # Roles - Strong contrast between User and Assistant
        "user": "deep_sky_blue1 bold",
        "assistant": "bright_white",

        # Tools - Vibrant neons to distinguish from regular text
        "tool": "medium_purple1 bold",
        "tool.read": "aquamarine1",
        "tool.write": "gold1",
        "tool.shell": "bright_magenta",
        "tool.network": "cornflower_blue",
        "tool.memory": "sea_green1",
        "tool.mcp": "cyan2",

        # Code / blocks - Crisp and readable
        "code": "grey93",
    }
)
# jaanbuchkar private rkaha taaki globally sirf ek hi instance bane and dusre files sirf get_console() se hi access kar paayenge saara
_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(theme=AGENT_THEME, highlight=False)

    return _console


class TUI:
    def __init__(self, console: Console | None = None) -> None:
        self.console = _console or get_console()
        self._assistant_stream_open = False
        # call id and all args for that tool, used for caching as they are needed in multiple event displays in the tui
        self._tool_args_by_call_id: dict[str, dict[str, Any]] = {}
        self.cwd = Path.cwd()

    def begin_assistant(self) -> None:
        self.console.print()  # for new line
        self.console.print(Rule(Text("Assistant", style="assistant")))
        self._assistant_stream_open = True

    def end_assistant(self) -> None:
        if self._assistant_stream_open:
            self.console.print()
        self._assistant_stream_open = False

    def stream_assistant_delta(self, content: str) -> None:
        self.console.print(content, end="", markup=False)

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
            table.add_row(key, value)

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
                display_args[key] = str(resolve_path(val, self.cwd))

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
