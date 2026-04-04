from dataclasses import field, dataclass
from enum import Enum
import os
from pathlib import Path
from typing import Any

from autopilot.config.config import MCPServerConfig

from fastmcp import Client
from fastmcp.client.transports import SSETransport, StdioTransport


class MCPServerStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPServerInfo:
    name: str
    description: str
    # Full inputSchema as received from the MCP server — preserved verbatim
    # so the LLM gets every type constraint, enum, description, and example.
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


class MCPClient:
    def __init__(self, name: str, config: MCPServerConfig, cwd: Path) -> None:
        self.name = name
        self.config = config
        self.cwd = cwd
        self.status = MCPServerStatus.DISCONNECTED
        self._client: Client | None = None
        self._tools: dict[str, MCPServerInfo] = {}

    @property
    def tools(self) -> list[MCPServerInfo]:
        return list(self._tools.values())

    def _create_transport(self) -> StdioTransport | SSETransport:
        if self.config.command:
            env = os.environ.copy()
            env.update(self.config.env)
            return StdioTransport(
                command=self.config.command,
                args=list(self.config.args),
                env=env,
                cwd=str(self.config.cwd or self.cwd),
                log_file=Path(os.devnull),
            )
        else:
            return SSETransport(url=self.config.url)  # type: ignore

    def _extract_input_schema(self, tool) -> dict[str, Any]:
        """
        fastmcp may expose the schema as either camelCase (inputSchema) or
        snake_case (input_schema) depending on the version. Try both so we
        never silently drop property descriptions and type constraints.
        """
        for attr in ("inputSchema", "input_schema"):
            schema = getattr(tool, attr, None)
            if schema and isinstance(schema, dict):
                return schema
        return {}

    async def connect(self) -> None:
        # Idempotent — safe to call multiple times
        if self.status == MCPServerStatus.CONNECTED:
            return
        self.status = MCPServerStatus.CONNECTING

        # __aenter__ / __aexit__ used directly (not `async with`) so the
        # connection stays alive for the lifetime of the process.
        try:
            self._client = Client(transport=self._create_transport())
            await self._client.__aenter__()

            tool_result = await self._client.list_tools()
            for tool in tool_result:
                schema = self._extract_input_schema(tool)
                self._tools[tool.name] = MCPServerInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=schema,
                    server_name=self.name,
                )
            self.status = MCPServerStatus.CONNECTED
        except Exception:
            self.status = MCPServerStatus.ERROR
            raise

    async def disconnect(self) -> None:
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
        self._tools.clear()
        self.status = MCPServerStatus.DISCONNECTED

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self._client or self.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(
                f"MCP server '{self.name}' is not connected "
                f"(status={self.status.value})"
            )

        result = await self._client.call_tool(tool_name, arguments)

        output_parts: list[str] = []
        for item in result.content:
            if hasattr(item, "text"):
                output_parts.append(item.text)  # type: ignore
            else:
                output_parts.append(str(item))

        return {
            "output":   "\n".join(output_parts),
            "is_error": result.is_error,
        }
