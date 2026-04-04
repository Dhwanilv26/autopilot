import asyncio
from pathlib import Path
import sys
import click

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path.cwd() / ".env")

from autopilot.agent.agent import Agent
from autopilot.agent.events import AgentEventType
from autopilot.agent.persistence_manager import PersistenceManager, SessionSnapshot
from autopilot.agent.session import Session
from autopilot.client.response import TokenUsage
from autopilot.config.config import ApprovalPolicy, Config
from autopilot.config.loader import load_config
from autopilot.ui.tui import TUI, get_console


from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML


console = get_console()

HISTORY_FILE = Path(".autopilot_history")


def read_history_entries(path: Path) -> list[str]:
    if not path.exists():
        return []

    lines = path.read_text().splitlines()

    entries = []
    current = []

    for line in lines:
        if line.startswith("+"):
            if current:
                entries.append("\n".join(current))
            current = [line[1:]]  # remove "+"
        else:
            current.append(line)

    if current:
        entries.append("\n".join(current))

    return entries


def write_history_entries(path: Path, entries: list[str]):
    lines = []
    for entry in entries:
        parts = entry.split("\n")
        lines.append("+" + parts[0])
        lines.extend(parts[1:])

    path.write_text("\n".join(lines) + "\n")


def trim_history(path: Path, max_entries: int = 25):
    entries = read_history_entries(path)
    trimmed = entries[-max_entries:]
    write_history_entries(path, trimmed)


def clear_history(path: Path):
    path.write_text("")


class CLI:
    def __init__(self, config: Config):
        self.agent: Agent | None = None
        self.config = config
        self.tui = TUI(config, console)

        self.session = PromptSession(
            history=FileHistory(str(HISTORY_FILE)),
            auto_suggest=AutoSuggestFromHistory(),
        )

    async def run_single(self, message: str) -> str | None:
        async with Agent(config=self.config) as agent:
            self.agent = agent
            trim_history(HISTORY_FILE, max_entries=25)
            return await self._process_message(message)

    async def run_interactive(self) -> str | None:
        self.tui.print_welcome("AI Agent", config=self.config)

        async with Agent(self.config, confirmation_callback=self.tui.handle_confirmation) as agent:
            self.agent = agent

            while True:
                try:
                    user_input = await self.session.prompt_async(
                        HTML("\n<ansiblue><b>></b></ansiblue> ")
                    )
                    user_input = user_input.strip()

                    if not user_input:
                        continue

                    if user_input.startswith("/"):
                        should_continue = await self._handle_command(user_input)
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

        assert self.agent.session is not None

        assistant_streaming = False
        final_response: str | None = None

        async for event in self.agent.run(message):

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

                tool = self.agent.session.tool_registry.get(tool_name)
                tool_kind = tool.kind.value if tool else None

                self.tui.tool_call_start(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("arguments", {})
                )

            elif event.type == AgentEventType.TOOL_CALL_COMPLETE:
                tool_name = event.data.get("name", "unknown")

                tool = self.agent.session.tool_registry.get(tool_name)
                tool_kind = tool.kind.value if tool else None

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

    async def _handle_command(self, command: str) -> bool:
        assert self.agent is not None
        assert self.agent.session is not None

        session = self.agent.session
        cmd = command.lower().strip()
        parts = cmd.split(maxsplit=1)
        cmd_name = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""

        # EXIT
        if cmd_name in ["/exit", "/quit"]:
            return False

        # HELP
        elif cmd_name == "/help":
            self.tui.show_help()

        # CLEAR
        elif cmd_name == "/clear":
            assert session.context_manager is not None
            assert session.loop_detector is not None

            session.context_manager.clear()
            session.loop_detector.clear()
            console.print("[success] Conversation cleared! [/success]")

        # CONFIG
        elif cmd_name == "/config":
            self.tui.render_config_table(self.config)

        # MODEL
        elif cmd_name == "/model":
            if cmd_args:
                self.config.model_name = cmd_args
                console.print(f"[success] Model changed to {cmd_args} [/success]")
            else:
                console.print(f"Current model: {self.config.model_name}")

        # APPROVAL
        elif cmd_name == "/approval":
            if cmd_args:
                try:
                    approval = ApprovalPolicy(cmd_args)
                    self.config.approval = approval
                    console.print(f"[success]Approval policy changed to: {cmd_args} [/success]")
                except Exception:
                    console.print(f"[error]Incorrect approval policy: {cmd_args} [/error]")
                    console.print(f"Valid options: {', '.join([p.value for p in ApprovalPolicy])}")
            else:
                console.print(f"Current approval policy: {self.config.approval.value}")

        # STATS
        elif cmd_name == "/stats":
            stats = session.get_stats()
            self.tui.render_stats_table(stats)

        # TOOLS
        elif cmd_name == "/tools":
            tools = session.tool_registry.get_tools()
            console.print(f"\n[bold]Available tools ({len(tools)}) [/bold]")
            for tool in tools:
                console.print(f"  • {tool.name}")

        # MCP
        elif cmd_name == "/mcp":
            mcp_servers = session.mcp_manager.get_all_servers()
            console.print(f"\n[bold]MCP Servers ({len(mcp_servers)}) [/bold]")
            for server in mcp_servers:
                status = server["status"]
                color = "green" if status == "connected" else "red"
                console.print(
                    f"  • {server['name']}: [{color}]{status}[/{color}] ({server['tools']} tools)"
                )

        # SAVE SESSION
        elif cmd_name == "/save":
            assert session.context_manager is not None

            persistence_manager = PersistenceManager()
            snapshot = SessionSnapshot(
                session_id=session.session_id,
                created_at=session.created_at,
                updated_at=session.updated_at,
                turn_count=session.turn_count,
                messages=session.context_manager.get_messages(),
                total_usage=session.context_manager.total_usage
            )

            persistence_manager.save_session(snapshot)
            console.print(f"[success] Session saved: {session.session_id} [/success]")

        # LIST SESSIONS
        elif cmd_name == "/sessions":
            persistence_manager = PersistenceManager()
            sessions = persistence_manager.list_sessions()

            console.print("\n[bold]Saved Sessions[/bold]")
            for s in sessions:
                console.print(
                    f"  • {s['session_id']} (turns: {s['turn_count']}, updated: {s['updated_at']})"
                )

        # CHECKPOINT LIST
        elif cmd_name == "/checkpoints":
            persistence_manager = PersistenceManager()
            checkpoints = persistence_manager.list_checkpoints()

            console.print("\n[bold]Saved Checkpoints[/bold]")
            for c in checkpoints:
                console.print(
                    f"  • {c['session_id']} (turns: {c['turn_count']}, updated: {c['updated_at']})"
                )

        # RESUME
        elif cmd_name == "/resume":
            if not cmd_args:
                console.print("[error]Usage: /resume <session_id> [/error]")
            else:
                persistence_manager = PersistenceManager()
                snapshot = persistence_manager.load_session(cmd_args)

                if not snapshot:
                    console.print(f"[error] Session does not exist [/error]")
                else:
                    new_session = Session(config=self.config)
                    await new_session.initialize()

                    assert new_session.context_manager is not None

                    new_session.session_id = snapshot.session_id
                    new_session.created_at = snapshot.created_at
                    new_session.updated_at = snapshot.updated_at

                    new_session.context_manager.total_usage = (
                        snapshot.total_usage or TokenUsage(0, 0)
                    )

                    await new_session.context_manager.load_from_snapshot(snapshot)

                    await session.client.close()
                    await session.mcp_manager.shutdown()

                    self.agent.session = new_session
                    console.print(f"[success]Resumed session: {new_session.session_id}[/success]")

        # CHECKPOINT CREATE
        elif cmd_name == "/checkpoint":
            assert session.context_manager is not None

            persistence_manager = PersistenceManager()
            snapshot = SessionSnapshot(
                session_id=session.session_id,
                created_at=session.created_at,
                updated_at=session.updated_at,
                turn_count=session.turn_count,
                messages=session.context_manager.get_messages(),
                total_usage=session.context_manager.total_usage
            )

            checkpoint_id = persistence_manager.save_checkpoint(snapshot)
            console.print(f"[success] Checkpoint created: {checkpoint_id}[/success]")

        # RESTORE
        elif cmd_name == "/restore":
            if not cmd_args:
                console.print("[error]Usage: /restore <checkpoint_id> [/error]")
            else:
                persistence_manager = PersistenceManager()
                snapshot = persistence_manager.load_checkpoint(cmd_args)

                if not snapshot:
                    console.print("[error]Checkpoint does not exist [/error]")
                else:
                    new_session = Session(config=self.config)
                    await new_session.initialize()

                    assert new_session.context_manager is not None

                    new_session.session_id = snapshot.session_id
                    new_session.created_at = snapshot.created_at
                    new_session.updated_at = snapshot.updated_at
                    new_session._turn_count = snapshot.turn_count

                    new_session.context_manager.total_usage = (
                        snapshot.total_usage or TokenUsage(0, 0)
                    )

                    for msg in snapshot.messages:
                        role = msg.get("role")
                        if role == "system":
                            continue
                        elif role == "user":
                            new_session.context_manager.add_user_message(msg.get("content", ""))
                        elif role == "assistant":
                            new_session.context_manager.add_assistant_message(
                                msg.get("content", ""), msg.get("tool_calls")
                            )
                        elif role == "tool":
                            new_session.context_manager.add_tool_result(
                                msg.get("tool_call_id", ""), msg.get("content", "")
                            )

                    await session.client.close()
                    await session.mcp_manager.shutdown()

                    self.agent.session = new_session
                    console.print(f"[success]Restored checkpoint: {cmd_args}[/success]")

        elif cmd_name == "/history":
            entries = read_history_entries(HISTORY_FILE)

            if not entries:
                console.print("[dim]No history found[/dim]")
            else:
                console.print("\n[bold]History[/bold]")
                for i, entry in enumerate(entries[-10:], 1):
                    console.print(f"{i}. {entry}")

        elif cmd_name == "/history-clear":
            clear_history(HISTORY_FILE)

            # reset prompt session too
            self.session = PromptSession(
                history=FileHistory(str(HISTORY_FILE)),
                auto_suggest=AutoSuggestFromHistory(),
            )

            console.print("[success]History cleared![/success]")

        elif cmd_name == "/history-trim":
            trim_history(HISTORY_FILE, max_entries=25)
            console.print("[success]History trimmed to last 25 entries[/success]")
        else:
            console.print(f'[error] Unknown command "{cmd_name}" [/error]')

        return True


@click.command()
@click.argument("prompt", required=False)
@click.option("--cwd", "-c", type=click.Path(exists=True, file_okay=False, path_type=Path))
def main(prompt: str | None, cwd: Path | None):
    try:
        config = load_config(cwd=cwd)
    except Exception as e:
        console.print(f"[error]configuration error : {e}[/error]")
        sys.exit(1)

    if config is None:
        console.print("[error]configuration error: failed to load configuration[/error]")
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


if __name__ == "__main__":
    main()
