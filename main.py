import asyncio
import sys
from typing import Any
import click

from agent.agent import Agent
from agent.events import AgentEventType
from client.llm_client import LLMClient
from ui.tui import TUI, get_console

console = get_console()


class CLI:
    def __init__(self):
        self.agent: Agent | None = None
        self.tui = TUI(console)

    async def run_single(self, message: str) -> str | None:
        async with Agent() as agent:
            self.agent = agent
            # return directly used as it is a run single function, and return await unwraps the coroutine here itself
            return await self._process_message(message)

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
                tool = self.agent.tool_registry.get(tool_name)
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

        return final_response


@click.command()
@click.argument("prompt", required=False)
def main(
    prompt: str | None,
):
    cli = CLI()
    # client = LLMClient()
    # messages = [{"role": "user", "content": prompt}]
    # yield value in the event variable

    # used async for instead of await to process the response in chunks and not wait till the entire response, and chat_completion returns an async generator
    if prompt:
        result = asyncio.run(cli.run_single(prompt))
        if result is None:
            sys.exit(1)


main()
