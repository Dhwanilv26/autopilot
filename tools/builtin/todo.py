from config.config import Config
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


class TodosParams(BaseModel):
    action: str

    id: str | None = None
    content: str | None = None
    contents: list | None = None

    priority: str | None = None
    status: str | None = None
    sort_by: str | None = None


class TodosTool(Tool):
    name = "todos"
    description = """
Advanced todo manager with batch support, per-task priority, status tracking.

IMPORTANT:
- ALWAYS use structured format for add_all:
  contents: [{"content": "...", "priority": "high"}]

- DO NOT send plain string lists if priority is important.

Examples:

Correct:
action: "add_all"
contents: [
  {"content": "Setup backend", "priority": "high"},
  {"content": "Write tests", "priority": "low"}
]

Incorrect:
contents: ["Setup backend", "Write tests"]
"""
    kind = ToolKind.MEMORY

    @property
    def schema(self):
        return TodosParams

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._todos: dict[str, dict] = {}

    def _now(self):
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    def _validate_priority(self, p):
        if not p:
            return "medium"
        p = p.lower()
        return p if p in ["low", "medium", "high"] else "medium"

    def _priority_value(self, p):
        return {"high": 3, "medium": 2, "low": 1}.get(p, 2)

    def _filter_and_sort(self, todos, status=None, sort_by=None):
        items = list(todos.items())

        if status:
            items = [(k, v) for k, v in items if v["status"] == status]

        if sort_by == "priority":
            items.sort(key=lambda x: self._priority_value(x[1]["priority"]), reverse=True)
        elif sort_by == "created_at":
            items.sort(key=lambda x: x[1]["created_at"])

        return items

    def _format_grouped_table(self, items):
        if not items:
            return "No todos"

        groups = {
            "pending": [],
            "in_progress": [],
            "completed": []
        }

        for tid, t in items:
            groups[t["status"]].append((tid, t))

        lines = []

        for status, group_items in groups.items():
            if not group_items:
                continue

            id_width = max(len("ID"), *(len(tid) for tid, _ in group_items))
            priority_width = max(len("PRIORITY"), *(len(t["priority"]) for _, t in group_items))
            task_width = max(len("TASK"), *(len(t["content"]) for _, t in group_items))
            task_width = min(task_width, 50)

            lines.append(f"\n=== {status.upper()} ===")

            header = (
                f"{'ID'.ljust(id_width)} | "
                f"{'PRIORITY'.ljust(priority_width)} | "
                f"{'TASK'.ljust(task_width)}"
            )

            separator = (
                f"{'-'*id_width}-+-"
                f"{'-'*priority_width}-+-"
                f"{'-'*task_width}"
            )

            lines.append(header)
            lines.append(separator)

            for tid, t in group_items:
                content = t["content"]
                if len(content) > task_width:
                    content = content[:task_width - 3] + "..."

                row = (
                    f"{tid.ljust(id_width)} | "
                    f"{t['priority'].ljust(priority_width)} | "
                    f"{content.ljust(task_width)}"
                )

                lines.append(row)

        return "\n".join(lines)

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = TodosParams(**invocation.params)
        action = params.action.lower()

        if action == "add":
            if not params.content:
                return ToolResult.error_result("'content' required")

            tid = str(uuid.uuid4())[:8]
            now = self._now()

            self._todos[tid] = {
                "content": params.content,
                "status": "pending",
                "priority": self._validate_priority(params.priority),
                "created_at": now,
                "updated_at": now
            }

            table = self._format_grouped_table(self._todos.items())
            return ToolResult.success_result(f"Added [{tid}]\n{table}")

        elif action == "add_all":
            if not params.contents:
                return ToolResult.error_result("'contents' required")

            now = self._now()

            for item in params.contents:
                if isinstance(item, dict):
                    content = item.get("content")
                    priority = self._validate_priority(item.get("priority"))
                else:
                    content = item
                    priority = self._validate_priority(params.priority)

                if not content or not content.strip():
                    continue

                tid = str(uuid.uuid4())[:8]

                self._todos[tid] = {
                    "content": content.strip(),
                    "status": "pending",
                    "priority": priority,
                    "created_at": now,
                    "updated_at": now
                }

            table = self._format_grouped_table(self._todos.items())
            return ToolResult.success_result(f"Added todos\n{table}")

        elif action == "start":
            if not params.id or params.id not in self._todos:
                return ToolResult.error_result("Valid 'id' required")

            self._todos[params.id]["status"] = "in_progress"
            self._todos[params.id]["updated_at"] = self._now()

            table = self._format_grouped_table(self._todos.items())
            return ToolResult.success_result(f"Started [{params.id}]\n{table}")

        elif action == "complete":
            if not params.id or params.id not in self._todos:
                return ToolResult.error_result("Valid 'id' required")

            self._todos[params.id]["status"] = "completed"
            self._todos[params.id]["updated_at"] = self._now()

            table = self._format_grouped_table(self._todos.items())
            return ToolResult.success_result(f"Completed [{params.id}]\n{table}")

        elif action == "update":
            if not params.id or params.id not in self._todos:
                return ToolResult.error_result("Valid 'id' required")

            if params.content:
                self._todos[params.id]["content"] = params.content

            if params.priority:
                self._todos[params.id]["priority"] = self._validate_priority(params.priority)

            self._todos[params.id]["updated_at"] = self._now()

            table = self._format_grouped_table(self._todos.items())
            return ToolResult.success_result(f"Updated [{params.id}]\n{table}")

        elif action == "list":
            items = self._filter_and_sort(
                self._todos,
                status=params.status,
                sort_by=params.sort_by
            )

            table = self._format_grouped_table(items)
            return ToolResult.success_result(table)

        elif action == "clear":
            count = len(self._todos)
            self._todos.clear()
            return ToolResult.success_result(f"Cleared {count} todos")

        else:
            return ToolResult.error_result(f"Unknown action: {params.action}")
