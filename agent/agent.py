from typing import AsyncGenerator

from agent.events import AgentEvent

class Agent:
    def __init__(self):
        pass

    async def __agentic_loop(self) -> AsyncGenerator[AgentEvent]
