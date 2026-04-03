import json
from typing import Any

from agent.persistence_manager import PersistenceManager
from client.llm_client import LLMClient
from config.config import Config
from context.compaction import ChatCompactor
from context.loop_detector import LoopDetector
from context.manager import ContextManager
from hooks.hook_system import HookSystem
from safety.approval import ApprovalManager
from tools.discovery import ToolDiscoveryManager
from tools.mcp.mcp_manager import MCPManager
from tools.registry import create_default_registry
from datetime import datetime
from config.loader import get_data_dir


class Session:
    # async can not be inside __init__
    def __init__(self, config: Config, confirmation_callback=None) -> None:
        self.config = config
        self.client = LLMClient(config=config)
        self.tool_registry = create_default_registry(config)
        self.context_manager: ContextManager | None = None
        # subagent banate time -> new agent to obviously new session
        self.discovery_manager = ToolDiscoveryManager(
            self.config,
            self.tool_registry,
        )
        self.mcp_manager = MCPManager(self.config)
        self.chat_compactor = ChatCompactor(self.client)
        self.approval_manager = ApprovalManager(
            self.config.approval, self.config.cwd, confirmation_callback=confirmation_callback)
        self.loop_detector = LoopDetector()
        self.hook_system = HookSystem(self.config)
        pm = PersistenceManager()
        self.session_id = pm.generate_session_id()
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

        self._turn_count = 0

    @property
    def turn_count(self) -> int:
        return self._turn_count

        # these are heavy operations directly inside the constructor, also await cant be used inside a constructor, so moved them into another function, only store objects inside constructor and dont execute anything else
    async def initialize(self) -> None:
        await self.mcp_manager.initialize()
        self.mcp_manager.register_tools(self.tool_registry)
        self.discovery_manager.discover_all()
        self.context_manager = ContextManager(
            config=self.config,
            user_memory=self._load_memory(),
            tools=self.tool_registry.get_tools()
        )

    def _load_memory(self) -> str | None:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir/"user_memory.json"

        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
            entries = data.get("entries")

            if not entries:
                return None

            lines = ["User preferences and notes:"]

            for key, value in entries.items():
                lines.append(f"-{key}:{value}")

            return "\n".join(lines)
        except Exception:
            return None

    def increment_turn(self) -> int:
        self._turn_count += 1
        self.updated_at = datetime.now()

        return self._turn_count

    def format_datetime(self, dt_str: str) -> str:
        dt = datetime.fromisoformat(dt_str)
        hour = dt.strftime("%I").lstrip("0")
        return f"{hour}:{dt.strftime('%M %p, %d %B %Y')}"

    def get_stats(self) -> dict[str, Any]:
        assert self.context_manager is not None
        return {
            "session_id": self.session_id,
            "created_at": self.format_datetime(self.created_at.isoformat()),
            "turn_count": self._turn_count,
            "message_count": self.context_manager.message_count,
            "token_usage": self.context_manager.total_usage.pretty(),
            "tools_count": len(self.tool_registry.get_tools()),
            "mcp_tools": len(self.tool_registry.connected_mcp_tools)
        }
