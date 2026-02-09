from typing import Any
from client.llm_client import LLMClient
import asyncio
import click

class CLI:
    def __init__(self):
        pass

    def run_single(self):
        pass


async def run(messages: list[dict[str, Any]]):
    client = LLMClient()
    async for event in client.chat_completion(messages, True):
        print(event)


# entire fn wrapped up in a cli thing
@click.command()
@click.argument("prompt", required=False)
def main(
    prompt: str | None,
):
    print(prompt)
    client = LLMClient()
    messages = [{"role": "user", "content": prompt}]
    # yield value in the event variable

    # used async for instead of await to process the response in chunks and not wait till the entire response, and chat_completion returns an async generator
    asyncio.run(run(messages))
    print("done")


main()
