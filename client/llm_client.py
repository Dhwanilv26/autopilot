from openai import AsyncOpenAI
from typing import Any


class LLMClient:
    def __init__(self) -> None:
        # initialising the client first
        # client is a private variable, can have only 2 types asyncopenai or none, = is the default value
        self._client: AsyncOpenAI | None = None

    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            # this is just to establish a connection to the server, model is used to actually send prompts
            self._client = AsyncOpenAI(
                api_key="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",
                base_url="https://openrouter.ai/api/v1"
            )
        return self._client

    # overriding openai close method, client gets it from inheritance, as it is an instance fo asyncopenai
    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    # messages is the total context here consisting of user and assistant prompts, vector<pair<string,any>> type, each dict as role and msg value

    # to get a response from an llm, directly call this method only (abstracting openais chat completion method)
    async def chat_completion(self,
                              messages: list[dict[str, Any]],
                              stream: bool = True):
        client = self.get_client()
        # msgs,stream sab aa gaya kwargs mai
        kwargs = {
            "model": "nvidia/nemotron-3-nano-30b-a3b:free",
            "messages": messages,
            "stream": stream
        }
        if stream:
            await self._stream_response()
        else:
            await self._non_stream_response(client, kwargs)

    async def _stream_response(self):
        pass

    async def _non_stream_response(self,
                                   client: AsyncOpenAI,
                                   kwargs: dict[str, Any]):
        # spreading the kwargs like ... in js
        response = await client.chat.completions.create(**kwargs)
        print(response)
