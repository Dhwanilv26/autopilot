from pathlib import Path
from typing import Any
from tools.base import Tool, ToolInvocation, ToolResult
import logging
logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logging.warning(f"overwriting existing tool: {tool.name}")

        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Tool | None:
        if name in self._tools:
            return self._tools[name]
        return None

    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        # check for mcp too (later)
        return False

    def get_tools(self) -> list[Tool]:
        tools: list[Tool] = []

        for tool in self._tools.values():
            tools.append(tool)
        return tools

    def get_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self.get_tools()]

    async def invoke(self, name: str, params: dict[str, Any], cwd: Path | None):
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
        
        await tool.execute()
