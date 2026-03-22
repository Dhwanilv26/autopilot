from pathlib import Path
from typing import Any
from config.config import Config
from tools.base import Tool, ToolInvocation, ToolResult
import logging

from tools.builtin import get_all_builtin_tools
from tools.subagents.subagent_registry import get_default_subagent_definitions
from tools.subagents.subagents import SubAgentTool

# __name__ = name of the current module
logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self, config: Config):
        self._tools: dict[str, Tool] = {}
        self._mcp_tools: dict[str, Tool] = {}
        self.config = config

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning(f"overwriting existing tool: {tool.name}")

        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def register_mcp_tool(self, tool: Tool) -> None:

        self._mcp_tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Tool | None:
        if name in self._tools:
            return self._tools[name]
        elif name in self._mcp_tools:
            return self._mcp_tools[name]
        return None

    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        # check for mcp too (later)
        return False

    # runs everytime whenever an LLM needs tool_calls
    def get_tools(self) -> list[Tool]:
        tools: list[Tool] = []
        # values -> only the V in [K,V] pair
        for tool in self._tools.values():
            tools.append(tool)

        for mcp_tool in self._mcp_tools.values():
            tools.append(mcp_tool)

        if self.config.allowed_tools:
            allowed_set = set(self.config.allowed_tools)
            tools = [t for t in tools if t.name in allowed_set]
        return tools

    def get_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self.get_tools()]

    async def invoke(self, name: str, params: dict[str, Any], cwd: Path) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult.error_result(f"unknown tool: {name}",
                                           metadata={"tool_name": name})

        validation_errors = tool.validate_params(params)

        if validation_errors:
            return ToolResult.error_result(
                f"Invalid parameters: {':'.join(validation_errors)}",
                metadata={
                    "tool_name": name,
                    "validation_errors": validation_errors})

        invocation = ToolInvocation(params=params, cwd=cwd)

        try:
            result = await tool.execute(invocation)
        except Exception as e:
            logger.exception(f"tool {name} raised unexpected error")
            result = ToolResult.error_result(
                f"internal error: {str(e)}",
                metadata={"tool_name", name}
            )
        return result

# runs at the start of execution


def create_default_registry(config: Config) -> ToolRegistry:
    registry = ToolRegistry(config)

    for tool_class in get_all_builtin_tools():
        registry.register(tool_class(config))

    for subagent_def in get_default_subagent_definitions():
        registry.register(SubAgentTool(config, subagent_def))

    return registry
