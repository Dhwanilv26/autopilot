from client.llm_client import LLMClient
import asyncio


async def main():
    client = LLMClient()
    messages = [{"role": "user", "content": "what is up"}]
    # yield value in the event variable

    # used async for instead of await to process the response in chunks and not wait till the entire response, and chat_completion returns an async generator
    async for event in client.chat_completion(messages, stream=True):
        print(event)

    print("done")


# python is a synchronous language, we need asyncio for the main function to run
asyncio.run(main())
