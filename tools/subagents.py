import asyncio
from typing import Any

from pydantic import BaseModel, Field

from agent.agent import Agent
from agent.events import AgentEvent
from config.config import Config
from tools.base import Tool, ToolInvocation, ToolResult
from dataclasses import dataclass


class SubAgentParams(BaseModel):
    goal: str = Field(..., description="The specific task or goal for the subagent to accomplish.")


@dataclass
class SubAgentDefinition:
    name: str
    description: str
    goal_prompt: str
    allowed_tools: list[str] | None = None
    max_turns: int = 20
    timeout_seconds: float = 600


class SubAgentTool(Tool):
    def __init__(self, config: Config, definition: SubAgentDefinition) -> None:
        super().__init__(config)
        self.definition = definition

    @property
    def name(self) -> str:
        return f"subagent_{self.definition.name}"

    @property
    def description(self) -> str:
        return f"subagent_{self.definition.description}"

    @property
    def schema(self):
        return SubAgentParams

    def is_mutating(self, params: dict[str, Any]) -> bool:
        return True

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = SubAgentParams(**invocation.params)

        if not params.goal:
            return ToolResult.error_result("no goal was specified for subagent")
        config_dict = self.config.to_dict()
        config_dict['max_turns'] = self.definition.max_turns

        if self.definition.allowed_tools:
            config_dict['allowed_tools'] = self.definition.allowed_tools

        subagent_config = Config(**config_dict)

        prompt = f"""You are a specialized sub-agent with a specific task to complete.

        {self.definition.goal_prompt}

        YOUR TASK:
        {params.goal}

        IMPORTANT:
        - Focus only on completing the specified task
        - Do not engage in unrelated actions
        - Once you have completed the task or have the answer, provide your final response
        - Be concise and direct in your output
        """

        tool_calls = []
        final_response = None
        error = None
        terminate_response = "goal"
        try:
            async with Agent(self.config) as agent:
                deadline = asyncio.get_event_loop().time()+self.definition.timeout_seconds
                async for event in agent.run(prompt):
                    if asyncio.get_event_loop().time() > deadline:
                        terminate_response = "timeout"
                        final_response = "sub-agent timed out"
                        break
                    if event.type == AgentEvent.tool_call_start:
                        tool_calls.append(event.data.get("name"))
                    elif event.type == AgentEvent.text_complete:
                        final_response = event.data.get("content")
                    elif event.type == AgentEvent.agent_error:
                        terminate_response = "error"
                        error = event.data.get("error", "unknown")
                        final_response = f"sub-agent error: {error}"
                        break
        except Exception as e:
            terminate_response = "error"
            error = str(e)
            final_response = f"sub-agent failed : {e}"

        result = f"""
        Sub-agent '{self.definition.name} completed.'
        Termination: {terminate_response}
        Tools called: {', '.join(tool_calls) if tool_calls else 'None'}
        
        Result: {final_response or 'No response'}
        """

        if error:
            return ToolResult.error_result(result)
        return ToolResult.success_result(result)
