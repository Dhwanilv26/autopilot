import asyncio
import random
from openai import APIConnectionError, APIError, AsyncOpenAI
from typing import Any, AsyncGenerator
from openai import RateLimitError
from client.response import EventType, StreamEvent, TextDelta, TokenUsage


class LLMClient:
    def __init__(self) -> None:
        # initialising the client first
        # client is a private variable, can have only 2 types asyncopenai or none, = is the default value
        self._client: AsyncOpenAI | None = None
        self._max_retries: int = 3

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
                              stream: bool = True) -> AsyncGenerator[StreamEvent, None]:
        # rate limiting till 3 retries for both streamed and non streamed responses
        client = self.get_client()
        # msgs,stream sab aa gaya kwargs mai
        kwargs = {
            "model": "nvidia/nemotron-3-nano-30b-a3b:free",
            "messages": messages,
            "stream": stream
        }
        for attempt in range(self._max_retries+1):
            try:
                if stream:
                    async for event in self._stream_response(client, kwargs):
                        yield event

                else:
                    event = await self._non_stream_response(client, kwargs)
                    yield event  # return partially, send control back to main.py, comeback here and complete the rest of the data
                    # for non streaming response, yield only 1 event

                # return hai isiliye 1 sucessful baari mai sab aa gya varna except block mai jaata
                return

            except RateLimitError as e:
                if attempt < self._max_retries:
                    # implementing exponential backoff, to reduce server load and setting the thread to sleep
                    wait_time = 2**attempt  # 2^attempt
                    await asyncio.sleep(wait_time+random.random())

                else:
                    yield StreamEvent(
                        type=EventType.ERROR,
                        error=f"Rate limit exceeded : {e}"
                    )
                    return  # not allowing user to send prompts, agar koi bhi error aa gya in 3 mai se , else statement mai return likha hai isilye

            # agar api se connect karte time error aaya to, like network issue etc
            except APIConnectionError as e:
                if attempt < self._max_retries:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time+random.random())

                else:
                    yield StreamEvent(
                        type=EventType.ERROR,
                        error=f"Connection error : {e}"
                    )
                    return
            # agar api mai khud error aa gaya to
            except APIError as e:
                if attempt < self._max_retries:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time+random.random())

                else:
                    yield StreamEvent(
                        type=EventType.ERROR,
                        error=f"API error : {e}"
                    )
                    return

    async def _stream_response(self,
                               client: AsyncOpenAI,
                               kwargs: dict[str, Any]) -> AsyncGenerator[StreamEvent, None]:

        response = await client.chat.completions.create(**kwargs)

        usage: TokenUsage | None = None
        finish_reason: str | None = None
        async for chunk in response:

            if hasattr(chunk, "usage") and chunk.usage:
                # just to calculate the usage at the last
                usage = TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                    cached_tokens=chunk.usage.prompt_tokens_details.cached_tokens
                )

            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason

            # printing only the chunks having content
            if delta.content:
                yield StreamEvent(
                    type=EventType.TEXT_DELTA,
                    text_delta=TextDelta(delta.content)
                )
        # then yielding the final chunk with the usage, without the text delta
        yield StreamEvent(
            type=EventType.MESSAGE_COMPLETE,
            finish_reason=finish_reason,
            usage=usage
        )

    async def _non_stream_response(self,
                                   client: AsyncOpenAI,
                                   kwargs: dict[str, Any]) -> StreamEvent:
        # spreading the kwargs like ... in js
        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message
        text_delta = None
        if message.content:
            text_delta = TextDelta(content=message.content)

            usage = None
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cached_tokens=response.usage.prompt_tokens_details.cached_tokens
            )

        return StreamEvent(
            type=EventType.MESSAGE_COMPLETE,  # cant have event of text-delta, the msg received is the final
            text_delta=text_delta,
            finish_reason=choice.finish_reason,
            usage=usage  # type: ignore
        )
