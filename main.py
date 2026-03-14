import asyncio
from pathlib import Path
import sys
import click

from agent.agent import Agent
from agent.events import AgentEventType
from config.config import Config
from config.loader import load_config
from ui.tui import TUI, get_console

from dotenv import load_dotenv
load_dotenv()

console = get_console()


class CLI:
    def __init__(self, config: Config):
        self.agent: Agent | None = None
        self.tui = TUI(console)
        self.config = config

    async def run_single(self, message: str) -> str | None:
        async with Agent(config=self.config) as agent:
            self.agent = agent
            # return directly used as it is a run single function, and return await unwraps the coroutine here itself
            return await self._process_message(message)

    async def run_interactive(self) -> str | None:
        self.tui.print_welcome(
            "AI Agent",
            lines=[
                f"model: nvidia/nemotron-3-nano-30b-a3b:free",
                f"cwd: {Path.cwd()}",
                "commands: /help /config /approval /model /exit"
            ]
        )
        async with Agent(self.config) as agent:
            self.agent = agent
            while True:
                try:
                    user_input = console.input("\n[user]>[/user]").strip()
                    if not user_input:
                        continue
                    await self._process_message(user_input)
                except KeyboardInterrupt:
                    console.print("\n[dim]Use /exit to quit [/dim]")
                except EOFError:
                    break

        console.print("\n[dim] Goodbye! [/dim]")

    async def _process_message(self, message: str) -> str | None:
        if not self.agent:
            return None

        assistant_streaming = False
        final_response: str | None = None

        async for event in self.agent.run(message):
            # print(event)
            if event.type == AgentEventType.TEXT_DELTA:
                content = event.data.get("content", "")
                if not assistant_streaming:
                    self.tui.begin_assistant()
                    assistant_streaming = True
                self.tui.stream_assistant_delta(content)

            elif event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")
                if assistant_streaming:
                    self.tui.end_assistant()
                    assistant_streaming = False

            elif event.type == AgentEventType.AGENT_ERROR:
                error = event.data.get("error", "unknown error")
                console.print(f"\n[error]Error: {error}[/error]")

            elif event.type == AgentEventType.TOOL_CALL_START:
                tool_name = event.data.get("name", "unknown")
                if not self.agent.session:
                    raise RuntimeError("Session missing")
                tool = self.agent.session.tool_registry.get(tool_name)
                tool_kind = None

                if tool and tool_kind:
                    tool_kind = tool.kind.value
                # tool_kind is a small case prefix just to attach the prefix "tool.{tool_kind}" for the border and styling shit
                self.tui.tool_call_start(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("arguments", {})
                )

            elif event.type == AgentEventType.TOOL_CALL_COMPLETE:
                tool_name = event.data.get("name", "unknown")
                tool = self.agent.session.tool_registry.get(tool_name)  # type: ignore
                tool_kind = None

                if tool and tool_kind:
                    tool_kind = tool.kind.value

                self.tui.tool_call_complete(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("success", False),
                    event.data.get("output", ""),
                    event.data.get("error"),
                    event.data.get("metadata"),
                    event.data.get("diff"),
                    event.data.get("truncated", False),
                )

        return final_response


@click.command()
@click.argument("prompt", required=False)
@click.option("--cwd",
              "-c",
              type=click.Path(exists=True, file_okay=False, path_type=Path),
              help="Current working directory")
def main(
    prompt: str | None,
    cwd: Path | None
):
    try:
        config = load_config(cwd=cwd)
    except Exception as e:
        console.print(f"[error]configuration error : {e}[/error]")
        sys.exit(1)

    if config is None:
        console.print(f"[error]configuration error: failed to load configuration[/error]")
        sys.exit(1)

    errors = config.get_validation_errors()

    if errors:
        for error in errors:
            console.print(f"[error]configuration error: {error}[/error]")

        sys.exit(1)
    cli = CLI(config)

    if prompt:
        result = asyncio.run(cli.run_single(prompt))
        if result is None:
            sys.exit(1)
    else:
        asyncio.run(cli.run_interactive())


main()
