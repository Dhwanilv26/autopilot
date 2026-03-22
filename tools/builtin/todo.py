import json
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from config.config import Config
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult


class TodosParams(BaseModel):
    action: str

    id: str | None = None
    content: str | None = None
    contents: list | None = None

    priority: str | None = None
    status: str | None = None
    sort_by: str | None = None

    # ── Fix: LLMs sometimes serialise the list as a JSON string instead of a
    #         real array.  Detect that and parse it transparently so the tool
    #         never blows up with "Input should be a valid list".
    @field_validator("contents", mode="before")
    # coerce contents is the field validator here (field validator se custom validation rules bana sakte)
    @classmethod
    def coerce_contents(cls, v):
        if isinstance(v, str):
            v = v.strip()
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            # Last resort: try replacing single quotes → double quotes
            try:
                parsed = json.loads(v.replace("'", '"'))
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return v


class TodosTool(Tool):
    name = "todos"

    # Clean, unambiguous description — no syntax errors, no mixed quotes.
    # The LLM copies examples literally, so the example MUST be valid JSON.
    description = """
Advanced todo manager with batch support, per-task priority, and status tracking.

Actions: add | add_all | start | complete | update | list | clear

add        – add a single todo
  content  : string  (required)
  priority : "high" | "medium" | "low"  (default: medium)

add_all    – add multiple todos at once (preferred for bulk inserts)
  contents : array of objects, each with "content" and optional "priority"
  Example:
    action: "add_all"
    contents: [
      {"content": "Setup backend", "priority": "high"},
      {"content": "Write tests",   "priority": "low"}
    ]

start      – mark a todo as in_progress    (requires id)
complete   – mark a todo as completed      (requires id)
update     – edit content or priority      (requires id)
list       – list todos, optional filters: status, sort_by (priority | created_at)
clear      – delete all todos

IMPORTANT: Always use add_all for multiple todos. Never output raw JSON in the
assistant message — call the tool directly.
"""

    kind = ToolKind.MEMORY

    @property
    def schema(self):
        return TodosParams

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._todos: dict[str, dict] = {}

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _validate_priority(self, p) -> str:
        if not p:
            return "medium"
        p = str(p).lower()
        return p if p in ("low", "medium", "high") else "medium"

    def _priority_value(self, p) -> int:
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

    def _format_grouped_table(self, items) -> str:
        """
        Plain-text fallback table used as the `output` string in ToolResult.
        The TUI renders its own Rich table from metadata; this is just the
        text representation for logging / non-TUI consumers.
        """
        if not items:
            return "No todos"

        groups: dict[str, list] = {"pending": [], "in_progress": [], "completed": []}
        for tid, t in items:
            groups[t["status"]].append((tid, t))

        lines: list[str] = []

        for status, group_items in groups.items():
            if not group_items:
                continue
            # * is just used to destructure all the lens obtained e.g, [2,5,3]
            id_w = max(len("ID"),       *(len(tid) for tid, _ in group_items))
            pri_w = max(len("PRIORITY"), *(len(t["priority"]) for _,   t in group_items))
            tsk_w = min(
                max(len("TASK"), *(len(t["content"]) for _, t in group_items)),
                60,
            )

            lines.append(f"\n=== {status.upper()} ===")
            lines.append(
                f"{'ID'.ljust(id_w)} | {'PRIORITY'.ljust(pri_w)} | {'TASK'.ljust(tsk_w)}"
            )
            lines.append(f"{'-'*id_w}-+-{'-'*pri_w}-+-{'-'*tsk_w}")

            for tid, t in group_items:
                content = t["content"]
                if len(content) > tsk_w:
                    content = content[: tsk_w - 3] + "..."
                lines.append(
                    f"{tid.ljust(id_w)} | {t['priority'].ljust(pri_w)} | {content.ljust(tsk_w)}"
                )

        return "\n".join(lines)

    def _success(self, message: str) -> ToolResult:
        """
        Return a ToolResult that carries the full todos dict in metadata so the
        TUI can render a proper Rich table instead of raw text.
        """
        table_text = self._format_grouped_table(self._todos.items())
        return ToolResult.success_result(
            output=f"{message}\n{table_text}",
            metadata={
                "type":  "todos",
                "todos": dict(self._todos),   # snapshot — immutable for this render
            },
        )

    # ── Execute ───────────────────────────────────────────────────────────────

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = TodosParams(**invocation.params)
        action = params.action.lower()

        # ── add ───────────────────────────────────────────────────────────────
        if action == "add":
            if not params.content:
                return ToolResult.error_result("'content' is required for action 'add'")

            tid = str(uuid.uuid4())[:8]
            now = self._now()
            self._todos[tid] = {
                "content":    params.content,
                "status":     "pending",
                "priority":   self._validate_priority(params.priority),
                "created_at": now,
                "updated_at": now,
            }
            return self._success(f"Added [{tid}]")

        # ── add_all ───────────────────────────────────────────────────────────
        elif action == "add_all":
            if not params.contents:
                return ToolResult.error_result("'contents' is required for action 'add_all'")

            now = self._now()
            added = 0

            for item in params.contents:
                if isinstance(item, dict):
                    content = item.get("content")
                    priority = self._validate_priority(item.get("priority"))
                elif isinstance(item, str):
                    content = item
                    priority = self._validate_priority(params.priority)
                else:
                    continue

                if not content or not str(content).strip():
                    continue

                tid = str(uuid.uuid4())[:8]
                self._todos[tid] = {
                    "content":    str(content).strip(),
                    "status":     "pending",
                    "priority":   priority,
                    "created_at": now,
                    "updated_at": now,
                }
                added += 1

            if added == 0:
                return ToolResult.error_result("No valid items found in 'contents'")

            return self._success(f"Added {added} todos")

        # ── start ─────────────────────────────────────────────────────────────
        elif action == "start":
            if not params.id or params.id not in self._todos:
                return ToolResult.error_result("Valid 'id' is required for action 'start'")

            self._todos[params.id]["status"] = "in_progress"
            self._todos[params.id]["updated_at"] = self._now()
            return self._success(f"Started [{params.id}]")

        # ── complete ──────────────────────────────────────────────────────────
        elif action == "complete":
            if not params.id or params.id not in self._todos:
                return ToolResult.error_result("Valid 'id' is required for action 'complete'")

            self._todos[params.id]["status"] = "completed"
            self._todos[params.id]["updated_at"] = self._now()
            return self._success(f"Completed [{params.id}]")

        # ── update ────────────────────────────────────────────────────────────
        elif action == "update":
            if not params.id or params.id not in self._todos:
                return ToolResult.error_result("Valid 'id' is required for action 'update'")

            if params.content:
                self._todos[params.id]["content"] = params.content
            if params.priority:
                self._todos[params.id]["priority"] = self._validate_priority(params.priority)

            self._todos[params.id]["updated_at"] = self._now()
            return self._success(f"Updated [{params.id}]")

        # ── list ──────────────────────────────────────────────────────────────
        elif action == "list":
            items = self._filter_and_sort(
                self._todos,
                status=params.status,
                sort_by=params.sort_by,
            )
            table = self._format_grouped_table(items)
            return ToolResult.success_result(
                output=table,
                metadata={
                    "type":  "todos",
                    "todos": dict(self._todos),
                },
            )

        # ── clear ─────────────────────────────────────────────────────────────
        elif action == "clear":
            count = len(self._todos)
            self._todos.clear()
            return ToolResult.success_result(
                output=f"Cleared {count} todos",
                metadata={"type": "todos", "todos": {}},
            )

        # ── unknown ───────────────────────────────────────────────────────────
        else:
            return ToolResult.error_result(
                f"Unknown action '{params.action}'. "
                f"Valid actions: add, add_all, start, complete, update, list, clear"
            )
