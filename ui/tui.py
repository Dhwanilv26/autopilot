from rich.console import Console
from rich.theme import Theme

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

    def stream_assistant_delta(self, content: str) -> None:
        self.console.print(content, end="", markup=False)
