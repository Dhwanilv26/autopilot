from __future__ import annotations
from pathlib import Path
from typing import AsyncGenerator

from agent.events import AgentEvent, AgentEventType
from client.response import StreamEventType, ToolCall, ToolResultMessage
from config.config import Config
import json
from agent.session import Session


class Agent:
    def __init__(self, config: Config):
        # all variables are specific to a session, to avoid memory leaks, context pollution and maintain isolation while focusing concurrency
        self.session: Session | None = Session(config=config)
        self.config = config

    async def run(self, message: str):
        final_response = None
        yield AgentEvent.agent_start(message)
        if not self.session:
            raise RuntimeError("Session missing")

        self.session.context_manager.add_user_message(message)

        try:
            async for event in self._agentic_loop():
                yield event

                if event.type == AgentEventType.TEXT_COMPLETE:
                    final_response = event.data.get("content")

        except Exception as e:
            print("AGENT LOOP CRASHED:", e)
            raise

        yield AgentEvent.agent_end(final_response)

    async def _agentic_loop(self) -> AsyncGenerator[AgentEvent, None]:

        max_turns = self.config.max_turns

        for turn_num in range(max_turns):
            if not self.session:
                raise RuntimeError("Session missing")
            # self.session.increment_turn()

            response_text = ""
            # print(self.context_manager.get_messages())

            if not self.session.client:
                raise RuntimeError("agent must be used in a 'async with' block")

            tool_schemas = self.session.tool_registry.get_schemas()

            tool_calls: list[ToolCall] = []

            async for event in self.session.client.chat_completion(
                    messages=self.session.context_manager.get_messages(),
                    tools=tool_schemas if tool_schemas else None,
                    stream=True
            ):
                # print(event)
                if event.type == StreamEventType.TEXT_DELTA:
                    if event.text_delta:
                        content = event.text_delta.content
                        # print("hello")
                        response_text += content
                        yield AgentEvent.text_delta(content)

                elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                    if event.tool_call:
                        tool_calls.append(event.tool_call)

                elif event.type == StreamEventType.ERROR:
                    yield AgentEvent.agent_end(event.error or "Unknown error occured.")
            # print("response_text is this", response_text)
            self.session.context_manager.add_assistant_message(
                response_text,
                (
                    [
                        {
                            "id": tc.call_id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                # loads to convert into python object like dict or list
                                # dumps to convert string to json object
                                "arguments": json.dumps(tc.arguments)
                            }
                        }
                        for tc in tool_calls
                    ]
                ) if tool_calls else None
            )

            if response_text:
                yield AgentEvent.text_complete(response_text)

            if not tool_calls:
                return

            tool_call_results: list[ToolResultMessage] = []
            for tool_call in tool_calls:
                yield AgentEvent.tool_call_start(
                    tool_call.call_id,
                    tool_call.name,
                    tool_call.arguments
                )

                result = await self.session.tool_registry.invoke(
                    name=tool_call.name,
                    params=tool_call.arguments,
                    cwd=Path.cwd()
                )

                yield AgentEvent.tool_call_complete(
                    tool_call.call_id,
                    tool_call.name,
                    result
                )
                # just formatting everything before adding to the global context to suit LLM formats
                tool_call_results.append(
                    ToolResultMessage(
                        tool_call_id=tool_call.call_id,
                        content=result.to_model_output(),
                        is_error=not result.success
                    )
                )

            for tool_result in tool_call_results:
                self.session.context_manager.add_tool_result(
                    tool_result.tool_call_id,
                    tool_result.content
                )

    # __ is used for reserved keywords and methods in python, aenter is for async enter

    async def __aenter__(self) -> Agent:
        return self

    async def __aexit__(self,
                        exc_type,
                        exc_val,
                        exc_tb) -> None:
        if self.session and self.session.client:
            await self.session.client.close()
            self.session = None
