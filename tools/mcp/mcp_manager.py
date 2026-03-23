import asyncio
import logging

from config.config import Config
from tools.mcp.client import MCPClient, MCPServerStatus
from tools.mcp.mcp_tool import MCPTool
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class MCPManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._clients: dict[str, MCPClient] = {}
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        mcp_configs = self.config.mcp_servers
        if not mcp_configs:
            return

        # Build client objects for every enabled server
        for name, server_config in mcp_configs.items():
            if not server_config.enabled:
                logger.debug("MCP server '%s' is disabled — skipping", name)
                continue
            self._clients[name] = MCPClient(
                name=name,
                config=server_config,
                cwd=self.config.cwd,
            )

        if not self._clients:
            self._initialized = True
            return

        # Launch all connections concurrently, each with its own per-server timeout.
        # return_exceptions=True means one failed server doesn't kill the others.
        connection_tasks = {
            name: asyncio.wait_for(
                client.connect(),
                timeout=client.config.startup_timeout_sec,
            )
            for name, client in self._clients.items()
        }

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*connection_tasks.values(), return_exceptions=True),
                timeout=15,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Global MCP init timeout (15 s) — some servers may not be ready"
            )
            results = []

        # Log the outcome for every server so failures are never silent
        for name, result in zip(connection_tasks.keys(), results):
            client = self._clients[name]
            if isinstance(result, BaseException):
                logger.warning(
                    "MCP server '%s' failed to connect: %s: %s",
                    name,
                    type(result).__name__,
                    result,
                )
                # Status was already set to ERROR inside MCPClient.connect()
            elif client.status == MCPServerStatus.CONNECTED:
                tool_count = len(client.tools)
                logger.info(
                    "MCP server '%s' connected — %d tool(s) available: %s",
                    name,
                    tool_count,
                    [t.name for t in client.tools],
                )
            else:
                logger.warning(
                    "MCP server '%s' ended in unexpected status: %s",
                    name,
                    client.status.value,
                )

        self._initialized = True

    def register_tools(self, registry: ToolRegistry) -> int:
        """
        Register all tools from connected MCP servers into the tool registry.
        Returns the number of tools registered.
        Logs a warning for every server that is not connected so missing tools
        are always visible at startup rather than silently absent.
        """
        count = 0

        for name, client in self._clients.items():
            if client.status != MCPServerStatus.CONNECTED:
                logger.warning(
                    "Skipping MCP server '%s' (status=%s) — its tools will not be available",
                    name,
                    client.status.value,
                )
                continue

            for tool_info in client.tools:
                mcp_tool = MCPTool(
                    tool_info=tool_info,
                    client=client,
                    config=self.config,
                    name=f"{client.name}__{tool_info.name}",
                )
                registry.register_mcp_tool(mcp_tool)
                count += 1
                logger.debug("Registered MCP tool: %s", mcp_tool.name)

        logger.info("MCP tools registered: %d", count)
        return count

    async def shutdown(self) -> None:
        if not self._clients:
            return

        disconnection_tasks = [
            client.disconnect() for client in self._clients.values()
        ]
        results = await asyncio.gather(*disconnection_tasks, return_exceptions=True)

        for name, result in zip(self._clients.keys(), results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Error disconnecting MCP server '%s': %s", name, result
                )

        self._clients.clear()
        self._initialized = False
        logger.info("MCPManager shut down")
