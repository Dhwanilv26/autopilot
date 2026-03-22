import asyncio

from config.config import Config
from tools.mcp.client import MCPClient, MCPServerStatus
from tools.mcp.mcp_tool import MCPTool
from tools.registry import ToolRegistry


class MCPManager:
    def __init__(self, config: Config):
        self.config = config
        self._clients: dict[str, MCPClient] = {}
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        # print("CONFIG OBJECT:", self.config)
        mcp_configs = self.config.mcp_servers
        # print("MCP SERVERS:", mcp_configs)

        if not mcp_configs:
            return

        for name, server_config in mcp_configs.items():
            if not server_config.enabled:
                continue
            self._clients[name] = MCPClient(
                name=name,
                config=server_config,
                cwd=self.config.cwd
            )
        # connection tasks are just initalized here, and not executed (they are just coroutines as of now)

        connection_tasks = [
            asyncio.wait_for(
                client.connect(),
                timeout=client.config.startup_timeout_sec
            )
            for client in self._clients.values()
        ]

        try:
            # asyncio.gather runs multiple coroutines concurrently
            # errors are returned instead of crashing
            await asyncio.wait_for(
                asyncio.gather(*connection_tasks, return_exceptions=True),
                timeout=15
            )
        except asyncio.TimeoutError:
            print("Global timeout: some MCP servers took too long")

        self._initialized = True

    def register_tools(self, registry: ToolRegistry) -> int:
        count = 0

        for client in self._clients.values():
            if client.status != MCPServerStatus.CONNECTED:
                continue

            for tool_info in client.tools:
                mcp_tool = MCPTool(
                    tool_info=tool_info,
                    client=client,
                    config=self.config,
                    name=f"{client.name}__{tool_info.name}"
                )
                registry.register_mcp_tool(mcp_tool)
                count += 1

        return count
