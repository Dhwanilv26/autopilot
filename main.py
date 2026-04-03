import asyncio
from pathlib import Path
import sys
import click

from agent.agent import Agent
from agent.events import AgentEventType
from agent.persistence_manager import PersistenceManager, SessionSnapshot
from config.config import ApprovalPolicy, Config
from config.loader import load_config
from ui.tui import TUI, get_console

from dotenv import load_dotenv
load_dotenv()

console = get_console()


class CLI:
    def __init__(self, config: Config):
        self.agent: Agent | None = None
        self.config = config
        self.tui = TUI(config, console)

    async def run_single(self, message: str) -> str | None:
        async with Agent(config=self.config) as agent:
            self.agent = agent
            # return directly used as it is a run single function, and return await unwraps the coroutine here itself
            return await self._process_message(message)

    async def run_interactive(self) -> str | None:
        # print("model_name is", self.config.model_name)
        self.tui.print_welcome(
            "AI Agent",
            lines=[
                f"model: {self.config.model_name} ",
                f"cwd: {self.config.cwd}",
                "commands: /help /config /approval /model /exit"
            ]
        )
        async with Agent(self.config, confirmation_callback=self.tui.handle_confirmation) as agent:
            self.agent = agent
            while True:
                try:
                    user_input = console.input("\n[user]>[/user]").strip()
                    if not user_input:
                        continue

                    if user_input.startswith("/"):
                        should_continue = self._handle_command(user_input)
                        if not should_continue:
                            break
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
                    event.data.get("exit_code", ""),
                    event.data.get("truncated", False)
                )

        return final_response

    def _handle_command(self, command: str) -> bool:

        assert self.agent and self.agent.session is not None

        cmd = command.lower().strip()
        parts = cmd.split(maxsplit=1)
        cmd_name = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""

        if cmd_name == "/exit" or cmd_name == "/quit":
            return False

        elif command == "/help":
            self.tui.show_help()

        elif command == "/clear":
            if self.agent and self.agent.session and self.agent.session.context_manager and self.agent.session.loop_detector:
                self.agent.session.context_manager.clear()
                self.agent.session.loop_detector.clear()
                console.print(f"[success] Conversation cleared! [/success]")

        elif command == "/config":
            console.print("\n[bold]Current Configuration[/bold]")
            console.print(f"  Model: {self.config.model_name}")
            console.print(f"  Temperature: {self.config.temperature}")
            console.print(f"  Approval: {self.config.approval.value}")
            console.print(f"  Working Dir: {self.config.cwd}")
            console.print(f"  Max Turns: {self.config.max_turns}")
            console.print(f"  Hooks Enabled: {self.config.hooks_enabled}")

        elif cmd_name == "/model":
            if cmd_args:
                self.config.model_name = cmd_args
                console.print(f'[success] Model changed to {cmd_args} [/success]')
            else:
                console.print(f"Current model: {self.config.model_name}")

        elif cmd_name == "/approval":
            if cmd_args:
                try:
                    approval = ApprovalPolicy(cmd_args)
                    self.config.approval = approval
                    console.print(
                        f"[success]Approval policy changed to: {cmd_args} [/success]"
                    )
                except:
                    console.print(
                        f"[error]Incorrect approval policy: {cmd_args} [/error]"
                    )
                    console.print(
                        f"Valid options: {', '.join(p for p in ApprovalPolicy)}"
                    )
            else:
                console.print(f"Current approval policy: {self.config.approval.value}")

        elif cmd_name == "/stats":
            assert self.agent and self.agent.session is not None
            stats = self.agent.session.get_stats()
            console.print("\n[bold] Session Statistics: [/bold]")
            for key, value in stats.items():
                console.print(f" {key}: {value}")

        elif cmd_name == "/tools":

            tools = self.agent.session.tool_registry.get_tools()
            console.print(f"\n[bold]Available tools ({len(tools)}) [/bold]")
            for tool in tools:
                console.print(f"  • {tool.name}")

        elif cmd_name == "/mcp":

            mcp_servers = self.agent.session.mcp_manager.get_all_servers()
            console.print(f"\n[bold]MCP Servers ({len(mcp_servers)}) [/bold]")
            for server in mcp_servers:
                status = server["status"]
                status_color = "green" if status == "connected" else "red"
                console.print(
                    f"  • {server['name']}: [{status_color}]{status}[/{status_color}] ({server['tools']} tools)"
                )
        elif cmd_name == "/save":
            assert self.agent.session.context_manager is not None
            persistence_manager = PersistenceManager()
            session_snapshot = SessionSnapshot(
                session_id=self.agent.session.session_id,
                created_at=self.agent.session.created_at,
                updated_at=self.agent.session.updated_at,
                turn_count=self.agent.session.turn_count,
                messages=self.agent.session.context_manager.get_messages()
            )

            persistence_manager.save_session(session_snapshot)

            console.print(f"[success] Session saved: {self.agent.session.session_id} [/success]")

        elif cmd_name == "/sessions":
            persistence_manager = PersistenceManager()
            sessions = persistence_manager.list_sessions()
            console.print("\n[bold]Saved Sessions[/bold]")
            for s in sessions:
                console.print(
                    f"  • {s['session_id']} (turns: {s['turn_count']}, updated: {s['updated_at']})"
                )

        else:
            console.print(f'[error] Unknown command" {cmd_name} [/error]')

        return True


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
