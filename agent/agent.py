from __future__ import annotations
from typing import AsyncGenerator

from agent.events import AgentEvent, AgentEventType
from client.llm_client import LLMClient
from client.response import StreamEventType
from context.manager import ContextManager
from tools.registry import create_default_registry


class Agent:
    def __init__(self):
        # all variables are specific to a session, to avoid memory leaks, context pollution and maintain isolation while focusing concurrency
        self.client = LLMClient()
        self.context_manager = ContextManager()
        self.tool_registry = create_default_registry()  # ToolRegistry() already called here

    async def run(self, message: str):
        final_response = None
        yield AgentEvent.agent_start(message)
        self.context_manager.add_user_message(message)

        async for event in self._agentic_loop():
            yield event

            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")

        yield AgentEvent.agent_end(final_response)

    async def _agentic_loop(self) -> AsyncGenerator[AgentEvent, None]:

        response_text = ""

        if not self.client:
            raise RuntimeError("agent must be used in a 'async with' block")

        tool_schemas = self.tool_registry.get_schemas()

        async for event in self.client.chat_completion(
                messages=self.context_manager.get_messages(),
                tools=tool_schemas if tool_schemas else None,
                stream=True
        ):

            if event.type == StreamEventType.TEXT_DELTA:
                if event.text_delta:
                    content = event.text_delta.content
                    response_text += content
                    yield AgentEvent.text_delta(content)

            elif event.type == StreamEventType.ERROR:
                yield AgentEvent.agent_end(event.error or "Unknown error occured.")

        self.context_manager.add_assistant_message(response_text)

        if response_text:
            yield AgentEvent.text_complete(response_text)

    # __ is used for reserved keywords and methods in python, aenter is for async enter
    async def __aenter__(self) -> Agent:
        return self

    async def __aexit__(self,
                        exc_type,
                        exc_val,
                        exc_tb) -> None:
        if self.client:
            await self.client.close()
            self.client = None
