import asyncio
import click

from agent.agent import Agent
from agent.events import AgentEventType
from client.llm_client import LLMClient


class CLI:
    def __init__(self):
        self.agent: Agent | None = None

    async def run_single(self, message: str):
        async with Agent() as agent:
            self.agent = agent
            self._process_message(message)

    async def _process_message(self, message: str) -> str | None:
        if not self.agent:
            return None

        async for event in self.agent.run(message):
            if event.type == AgentEventType.TEXT_DELTA:
                content = event.data.get("content", "")


async def run(messages: list[dict[str, Any]]):

    # entire fn wrapped up in a cli thing


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
        asyncio.run(cli.run_single(prompt))


main()
