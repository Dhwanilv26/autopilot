from dataclasses import field, dataclass
from enum import Enum
import os
from pathlib import Path
from typing import Any

from config.config import MCPServerConfig

from fastmcp import Client
from fastmcp.client.transports import SSETransport, StdioTransport


class MCPServerStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
# mcpserver refers to the client conection state to the server


@dataclass
class MCPServerInfo:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


class MCPClient:
    def __init__(self, name: str, config: MCPServerConfig, cwd: Path) -> None:
        self.name = name
        self.config = config
        self.cwd = cwd
        self.status = MCPServerStatus.DISCONNECTED
        self._client: Client | None = None

        self._tools: dict[str, MCPServerInfo] = dict()

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
                cwd=str(self.config.cwd or self.cwd)
            )
        else:
            return SSETransport(url=self.config.url)  # type: ignore

    async def connect(self) -> None:
        if self.status == MCPServerStatus.CONNECTED:
            return  # singleton connected instance chahiye
        self.status = MCPServerStatus.CONNECTING

        # with is not used here as aexit so auto close ho jaayega connection (hame persistent connection chahiye)
        try:
            self._client = Client(transport=self._create_transport())
            await self._client.__aenter__()

            tool_result = await self._client.list_tools()
            for tool in tool_result:
                self._tools[tool.name] = MCPServerInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=(
                        # some servers dont provide inputschema
                        tool.inputSchema if hasattr(tool, "inputSchema") else {}
                    ),
                    server_name=self.name
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

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]):
        if not self._client or self.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"not connected to server {self.name}")

        result = await self._client.call_tool(tool_name, arguments)

        output = []
        for item in result.content:
            if hasattr(item, "text"):
                output.append(item.text)  # type: ignore
            else:
                output.append(str(item))

        return {
            "output": "\n".join(output),
            "is_error": result.is_error
        }
