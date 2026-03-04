import asyncio
import random
from openai import APIConnectionError, APIError, AsyncOpenAI
from typing import Any, AsyncGenerator
from openai import RateLimitError
from client.response import StreamEventType, StreamEvent, TextDelta, TokenUsage, ToolCall, ToolCallDelta, parse_tool_call_arguments
from config.config import Config


class LLMClient:
    def __init__(self, config: Config) -> None:
        # initialising the client first
        # client is a private variable, can have only 2 types asyncopenai or none, = is the default value
        self._client: AsyncOpenAI | None = None
        self._max_retries: int = 3
        self.config = config

    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            # this is just to establish a connection to the server, model is used to actually send prompts
            self._client = AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url
            )
        return self._client

    # overriding openai close method, client gets it from inheritance, as it is an instance fo asyncopenai
    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    def _build_tools(self, tools: list[dict[str, Any]]):
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get(
                        "parameters", {
                            "type": "object",
                            "properties": {}
                        }
                    )
                }
            }

            for tool in tools
        ]

    # messages is the total context here consisting of user and assistant prompts, vector<pair<string,any>> type, each dict as role and msg value

    # to get a response from an llm, directly call this method only (abstracting openais chat completion method)
    async def chat_completion(self,
                              messages: list[dict[str, Any]],
                              tools: list[dict[str, Any]] | None = None,
                              stream: bool = True) -> AsyncGenerator[StreamEvent, None]:
        # rate limiting till 3 retries for both streamed and non streamed responses
        client = self.get_client()
        # msgs,stream sab aa gaya kwargs mai
        kwargs = {
            "model": "qwen/qwen3-vl-30b-a3b-thinking",
            "messages": messages,
            "stream": stream
        }
        if tools:
            kwargs["tools"] = self._build_tools(tools)
            # print(kwargs["tools"])
            kwargs["tool_choice"] = "auto"
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
                        type=StreamEventType.ERROR,
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
                        type=StreamEventType.ERROR,
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
                        type=StreamEventType.ERROR,
                        error=f"API error : {e}"
                    )
                    return

    async def _stream_response(self,
                               client: AsyncOpenAI,
                               kwargs: dict[str, Any]) -> AsyncGenerator[StreamEvent, None]:

        response = await client.chat.completions.create(**kwargs)

        usage: TokenUsage | None = None
        finish_reason: str | None = None
        # each index -> seq of tool call and then inner dict is for params passed for each tool call
        tool_calls: dict[int, dict[str, Any]] = {}

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
                    type=StreamEventType.TEXT_DELTA,
                    text_delta=TextDelta(delta.content)
                )

            if delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    idx = tool_call_delta.index

                    # initializing the custom dict tool_calls to store the mapping of the function number and its params

                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tool_call_delta.id or "",
                            "name": "",
                            "arguments": ""
                        }

                    # always execute tool call functions because in streaming events, we get the chunks in random order so better take all function and argument calls

                    if tool_call_delta.function:
                        if tool_call_delta.function.name:
                            # updating custom dict to include the name for the current tool index
                            tool_calls[idx]["name"] = tool_call_delta.function.name
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_START,
                                tool_call_delta=ToolCallDelta
                                # N-d array , same level par hi hai index and id
                                (call_id=tool_calls[idx]["id"],
                                    name=tool_call_delta.function.name)
                            )
                    # this is from the llm response schema
                        # print("helloooo")
                    if tool_call_delta.function and tool_call_delta.function.arguments:
                        # this is from the custom tool_call dict

                        tool_calls[idx]["arguments"] += tool_call_delta.function.arguments
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_DELTA,
                            tool_call_delta=ToolCallDelta
                            (call_id=tool_calls[idx]["id"],
                                name=tool_call_delta.function.name,
                                arguments_delta=tool_call_delta.function.arguments)
                        )

        for idx, tc in tool_calls.items():

            yield StreamEvent(
                type=StreamEventType.TOOL_CALL_COMPLETE,
                tool_call=ToolCall(
                    call_id=tc["id"],
                    name=tc["name"],
                    arguments=parse_tool_call_arguments(tc["arguments"]))
            )

        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finish_reason=finish_reason,
            usage=usage
        )

    async def _non_stream_response(self,
                                   client: AsyncOpenAI,
                                   kwargs: dict[str, Any]) -> StreamEvent:
        # spreading the kwargs like ... in js
        response = await client.chat.completions.create(**kwargs)
        print("raw response", response)
        choice = response.choices[0]
        message = choice.message
        text_delta = None
        if message.content:
            text_delta = TextDelta(content=message.content)

        tool_calls: list[ToolCall] = []

        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(call_id=tc.id,
                             name=tc.function.name,
                             arguments=parse_tool_call_arguments(tc.function.arguments)))

            usage = None
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cached_tokens=response.usage.prompt_tokens_details.cached_tokens
            )

        return StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,  # cant have event of text-delta, the msg received is the final
            text_delta=text_delta,
            finish_reason=choice.finish_reason,
            usage=usage  # type: ignore
        )
