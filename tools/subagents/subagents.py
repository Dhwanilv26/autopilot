import asyncio
from typing import Any

from pydantic import BaseModel, Field

from config.config import Config
from tools.base import Tool, ToolInvocation, ToolResult
from dataclasses import dataclass

# subagents are specialized tools only


class SubAgentParams(BaseModel):
    # actual runtime prompt given by LLM
    goal: str = Field(..., description="The specific task or goal for the subagent to accomplish.")
    # (e.g, please find the bugs and resolve them in main.py)


@dataclass
class SubAgentDefinition:
    name: str
    description: str
    goal_prompt: str  # static and defined by the developer
    # (e.g, your job is to only find bugs and resolve them)
    allowed_tools: list[str] | None = None
    max_turns: int = 20
    timeout_seconds: float = 600


class SubAgentTool(Tool):
    def __init__(self, config: Config, definition: SubAgentDefinition) -> None:
        super().__init__(config)
        self.definition = definition

    @property
    def name(self) -> str:  # type: ignore
        return f"subagent_{self.definition.name}"

    @property
    def description(self) -> str:  # type: ignore
        return f"subagent_{self.definition.description}"

    @property
    def schema(self):
        return SubAgentParams

    def is_mutating(self, params: dict[str, Any]) -> bool:
        return True

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = SubAgentParams(**invocation.params)
        from agent.agent import Agent
        from agent.events import AgentEventType
        # using lazy importing to avoid circular import,
        # agent.py calling subagent.py and subagent.py calling agent.py , agent.py is not even fully loaded when calling it from subagent.py, so importing it later when subagent.py file is loaded properly

        if not params.goal:
            return ToolResult.error_result("no goal was specified for subagent. (LLM failed to provide one)")
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
            async with Agent(subagent_config) as agent:
                # complete new agent with new session, prompt is the only context for the subagent
                deadline = asyncio.get_event_loop().time()+self.definition.timeout_seconds
                async for event in agent.run(prompt):
                    if asyncio.get_event_loop().time() > deadline:
                        terminate_response = "timeout"
                        final_response = "sub-agent timed out"
                        break
                    if event.type == AgentEventType.TOOL_CALL_START:
                        tool_calls.append(event.data.get("name"))
                    elif event.type == AgentEventType.TEXT_COMPLETE:
                        final_response = event.data.get("content")
                    elif event.type == AgentEventType.AGENT_END:
                        if final_response is None:
                            final_response = event.data.get('response')
                    elif event.type == AgentEventType.AGENT_ERROR:
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
            return ToolResult.error_result(
                result,
                metadata={
                    "agent": self.definition.name,
                    "termination": terminate_response,
                    "tools_used": tool_calls,
                    "error": error,
                }
            )
        return ToolResult.success_result(
            result,
            metadata={"agent": self.definition.name,
                      "termination": terminate_response,
                      "tools_used": tool_calls}


        )
