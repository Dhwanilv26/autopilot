import json
from pathlib import Path

from config.loader import get_data_dir
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field


class MemoryParams(BaseModel):
    action: str = Field(..., description="Action: 'set', 'get', 'complete', 'list', 'clear'")
    key: str | None = Field(
        None, description="Memory key (required for 'set', 'get', 'delete' action)")
    value: str | None = Field(None, description="Value to store (required for 'set' action)")


class MemoryTool(Tool):
    name = "memory"
    description = "Store and retrieve persistent memory. Use this to remember user preferences, important context or notes."
    kind = ToolKind.MEMORY

    @property
    def schema(self):
        return MemoryParams

    def _load_memory(self) -> dict:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir/"user_memory.json"

        if not path.exists():
            return {"entries": {}}

        try:
            content = path.read_text(encoding='utf-8')
            return json.loads(content)
        except Exception:
            return {"entries": {}}

    def _save_memory(self, memory: dict) -> None:
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir/"user_memory.json"
        # write_text always overrides content
        path.write_text(json.dumps(memory, indent=2, ensure_ascii=False))

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = MemoryParams(**invocation.params)

        if params.action.lower() == "set":
            if not params.key or not params.value:
                return ToolResult.error_result(
                    "'key' and 'value' are required for set action")

            memory = self._load_memory()
            memory["entries"][params.key] = params.value

            self._save_memory(memory)

            return ToolResult.success_result(
                f"set memory: {params.key}"
            )

        elif params.action.lower() == "get":
            if not params.key:
                return ToolResult.error_result("'key' required for 'get' action")

            memory = self._load_memory()
            if params.key not in memory["entries"]:
                return ToolResult.error_result(f"'key' not found in memory {params.key}")

            return ToolResult.success_result(
                f"memory found: {params.key}: {memory['entries'][params.key]}"
            )

        elif params.action.lower() == "delete":
            if not params.key:
                return ToolResult.error_result("'key' required for 'get' action")
            memory = self._load_memory()
            if params.key not in memory['entries']:
                return ToolResult.error_result(f"memory not found: {params.key}")

            del memory['entries'][params.key]
            self._save_memory(memory)

            return ToolResult.success_result(f"deleted memory: {params.key}")

        elif params.action == "list":
            memory = self._load_memory()
            entries = memory.get("entries", {})
            if not entries:
                return ToolResult.error_result(f"no memory stored")

            lines = ["stored memories"]

            for key, value in sorted(entries.items()):
                lines.append(f" {key}:{value}")

            return ToolResult.success_result("\n".join(lines))

        elif params.action.lower() == "clear":
            memory = self._load_memory()
            count = len(memory['entries'])
            memory['entries'] = {}
            self._save_memory(memory)
            return ToolResult.success_result(f"cleared {count} memory entries")

        else:
            return ToolResult.error_result(f"unknown action : {params.action}")
