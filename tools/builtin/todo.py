from config.config import Config
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


# -------------------------------
# PARAMS
# -------------------------------
class TodosParams(BaseModel):
    action: str

    id: str | None = None
    content: str | None = None
    contents: list[str] | None = None

    priority: str | None = None

    # filtering / sorting
    status: str | None = None
    sort_by: str | None = None  # "priority", "created_at"


# -------------------------------
# TOOL
# -------------------------------
class TodosTool(Tool):
    name = "todos"
    description = """
Advanced todo manager with:
- batch add (add_all)
- status tracking (pending → in_progress → completed)
- priority (low, medium, high)
- filtering + sorting
- grouped table output

IMPORTANT:
- Use add_all for multiple todos
- After adding todos, ALWAYS call 'list' to display the updated task table.
"""
    kind = ToolKind.MEMORY

    @property
    def schema(self):
        return TodosParams

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._todos: dict[str, dict] = {}

    # -------------------------------
    # HELPERS
    # -------------------------------
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

        # FILTER
        if status:
            items = [(k, v) for k, v in items if v["status"] == status]

        # SORT
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

            lines.append(f"\n=== {status.upper()} ===")

            header = f"{'ID':<10} | {'PRIORITY':<8} | TASK"
            lines.append(header)
            lines.append("-" * len(header))

            for tid, t in group_items:
                lines.append(
                    f"{tid:<10} | {t['priority']:<8} | {t['content']}"
                )

        return "\n".join(lines)

    # -------------------------------
    # EXECUTE
    # -------------------------------
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = TodosParams(**invocation.params)
        action = params.action.lower()

        # -------------------------------
        # ADD
        # -------------------------------
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

            return ToolResult.success_result(f"Added [{tid}]")

        # -------------------------------
        # ADD_ALL
        # -------------------------------
        elif action == "add_all":
            if not params.contents:
                return ToolResult.error_result("'contents' required")

            now = self._now()
            added = []

            for item in params.contents:
                if not item.strip():
                    continue

                tid = str(uuid.uuid4())[:8]

                self._todos[tid] = {
                    "content": item.strip(),
                    "status": "pending",
                    "priority": self._validate_priority(params.priority),
                    "created_at": now,
                    "updated_at": now
                }

                added.append((tid, item.strip()))

            lines = ["Added todos:"]
            for tid, content in added:
                lines.append(f"[{tid}]: {content}")

            return ToolResult.success_result("\n".join(lines))

        # -------------------------------
        # START
        # -------------------------------
        elif action == "start":
            if not params.id or params.id not in self._todos:
                return ToolResult.error_result("Valid 'id' required")

            self._todos[params.id]["status"] = "in_progress"
            self._todos[params.id]["updated_at"] = self._now()

            return ToolResult.success_result(f"Started [{params.id}]")

        # -------------------------------
        # COMPLETE
        # -------------------------------
        elif action == "complete":
            if not params.id or params.id not in self._todos:
                return ToolResult.error_result("Valid 'id' required")

            self._todos[params.id]["status"] = "completed"
            self._todos[params.id]["updated_at"] = self._now()

            return ToolResult.success_result(f"Completed [{params.id}]")

        # -------------------------------
        # UPDATE
        # -------------------------------
        elif action == "update":
            if not params.id or params.id not in self._todos:
                return ToolResult.error_result("Valid 'id' required")

            if params.content:
                self._todos[params.id]["content"] = params.content

            if params.priority:
                self._todos[params.id]["priority"] = self._validate_priority(params.priority)

            self._todos[params.id]["updated_at"] = self._now()

            return ToolResult.success_result(f"Updated [{params.id}]")

        # -------------------------------
        # LIST (ADVANCED)
        # -------------------------------
        elif action == "list":
            items = self._filter_and_sort(
                self._todos,
                status=params.status,
                sort_by=params.sort_by
            )

            table = self._format_grouped_table(items)

            return ToolResult.success_result(table)

        # -------------------------------
        # CLEAR
        # -------------------------------
        elif action == "clear":
            count = len(self._todos)
            self._todos.clear()
            return ToolResult.success_result(f"Cleared {count} todos")

        else:
            return ToolResult.error_result(f"Unknown action: {params.action}")
