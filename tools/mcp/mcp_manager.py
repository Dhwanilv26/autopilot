import asyncio

from config.config import Config
from tools.mcp.client import MCPClient


class MCPManager:
    def __init__(self, config: Config):
        self.config = config
        self._clients: dict[str, MCPClient] = {}
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        mcp_configs = self.config.mcp_servers

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

        connection_tasks = [
            asyncio.wait_for(
                client.connect(),
                timeout=client.config.startup_timeout_sec
            )
            for name, client in self._clients.items()
        ]

        await asyncio.gather(*connection_tasks, return_exceptions=True)

        self._initialized = True
