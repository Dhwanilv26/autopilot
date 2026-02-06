from openai import AsyncOpenAI
from typing import Any


class LLMClient:
    def __init__(self) -> None:
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
    async def chat_completion(self,
                              messages: list[dict[str, Any]],
                              stream: bool = True):
        client = self.get_client()
        if stream:
            self._stream_response()
        else:
            self._non_stream_response()

    async def _stream_response(self):
        pass

    async def _non_stream_response(self, client: AsyncOpenAI):
        pass
