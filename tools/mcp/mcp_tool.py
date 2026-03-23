from __future__ import annotations

import json
from typing import Any

from config.config import Config
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from tools.mcp.client import MCPClient, MCPServerInfo


# ─────────────────────────────────────────────────────────────────────────────
#  Argument validator
#  Runs before every MCP call so bad LLM output is caught immediately
#  with a precise, actionable error message rather than a cryptic server error.
# ─────────────────────────────────────────────────────────────────────────────

class MCPArgumentValidator:
    """
    Validates and lightly coerces a dict of arguments against a JSON Schema.

    Coercions performed (silent, non-lossy):
      - "true" / "false" string  →  bool
      - numeric string           →  int or float (when schema says integer/number)
      - single object/value      →  [value]  (when schema says array)

    Anything that cannot be coerced is reported as a typed, named error so
    the LLM can fix it in exactly one retry.
    """

    # Types the LLM commonly confuses
    _BOOL_STRINGS = {"true": True, "false": False, "1": True, "0": False}

    def __init__(self, schema: dict[str, Any]) -> None:
        self._schema = schema
        self._properties = schema.get("properties", {})
        self._required = schema.get("required", [])

    # ── Public entry point ────────────────────────────────────────────────────

    def validate_and_coerce(
        self, args: dict[str, Any], tool_name: str
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Returns (coerced_args, errors).
        If errors is non-empty the call should be aborted and the errors
        returned to the LLM verbatim.
        """
        errors: list[str] = []
        result: dict[str, Any] = {}

        # 1. Check required fields first — most common LLM mistake
        missing = [f for f in self._required if f not in args]
        if missing:
            schema_hint = self._schema_summary()
            errors.append(
                f"Missing required field(s): {', '.join(missing)}.\n"
                f"Required: {self._required}\n"
                f"Schema:\n{schema_hint}"
            )
            return args, errors  # no point continuing

        # 2. Validate and coerce each provided argument
        for key, value in args.items():
            prop_schema = self._properties.get(key)

            if prop_schema is None:
                # Unknown field — pass through (MCP server will reject if strict)
                result[key] = value
                continue

            coerced, err = self._coerce_field(key, value, prop_schema)
            if err:
                errors.append(err)
            else:
                result[key] = coerced

        return result, errors

    # ── Coercion helpers ──────────────────────────────────────────────────────

    def _coerce_field(
        self, key: str, value: Any, schema: dict[str, Any]
    ) -> tuple[Any, str | None]:
        expected_type = schema.get("type")
        enum_values = schema.get("enum")

        # Enum check first (type may be absent for enums)
        if enum_values is not None:
            if value not in enum_values:
                # Try case-insensitive match for string enums
                if isinstance(value, str):
                    match = next(
                        (e for e in enum_values if str(e).lower() == value.lower()),
                        None,
                    )
                    if match is not None:
                        return match, None
                return value, (
                    f"Field '{key}': value {value!r} is not one of the allowed values: "
                    f"{enum_values}."
                )

        if expected_type is None:
            return value, None

        # ── boolean ──────────────────────────────────────────────────────────
        if expected_type == "boolean":
            if isinstance(value, bool):
                return value, None
            if isinstance(value, str) and value.lower() in self._BOOL_STRINGS:
                return self._BOOL_STRINGS[value.lower()], None
            return value, (
                f"Field '{key}': expected boolean, got {type(value).__name__} ({value!r}). "
                f"Use true or false (not a string)."
            )

        # ── integer ──────────────────────────────────────────────────────────
        if expected_type == "integer":
            if isinstance(value, bool):
                return value, (
                    f"Field '{key}': expected integer, got boolean. "
                    f"Use a number like 1 or 0."
                )
            if isinstance(value, int):
                return value, None
            if isinstance(value, str):
                try:
                    return int(value), None
                except ValueError:
                    pass
            if isinstance(value, float) and value.is_integer():
                return int(value), None
            return value, (
                f"Field '{key}': expected integer, got {type(value).__name__} ({value!r})."
            )

        # ── number ───────────────────────────────────────────────────────────
        if expected_type == "number":
            if isinstance(value, bool):
                return value, (
                    f"Field '{key}': expected number, got boolean."
                )
            if isinstance(value, (int, float)):
                return value, None
            if isinstance(value, str):
                try:
                    return float(value), None
                except ValueError:
                    pass
            return value, (
                f"Field '{key}': expected number, got {type(value).__name__} ({value!r})."
            )

        # ── string ───────────────────────────────────────────────────────────
        if expected_type == "string":
            if isinstance(value, str):
                return value, None
            # Coerce primitives to string silently
            if isinstance(value, (int, float, bool)):
                return str(value), None
            return value, (
                f"Field '{key}': expected string, got {type(value).__name__} ({value!r})."
            )

        # ── array ────────────────────────────────────────────────────────────
        if expected_type == "array":
            if isinstance(value, list):
                return value, None
            # LLMs often send a single object when an array of one is expected
            return [value], None

        # ── object ───────────────────────────────────────────────────────────
        if expected_type == "object":
            if isinstance(value, dict):
                return value, None
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        return parsed, None
                except json.JSONDecodeError:
                    pass
            return value, (
                f"Field '{key}': expected object (dict), got {type(value).__name__} ({value!r})."
            )

        return value, None

    # ── Schema summary for error messages ─────────────────────────────────────

    def _schema_summary(self) -> str:
        """Compact single-line-per-field summary shown in error messages."""
        if not self._properties:
            return "  (no schema available)"
        lines: list[str] = []
        for field_name, prop in self._properties.items():
            req_marker = "*" if field_name in self._required else " "
            type_str = prop.get("type", "any")
            desc = prop.get("description", "")
            enum_str = f", one of {prop['enum']}" if "enum" in prop else ""
            lines.append(
                f"  {req_marker} {field_name}: {type_str}{enum_str}"
                + (f" — {desc}" if desc else "")
            )
        return "\n".join(lines)


class MCPTool(Tool):

    def __init__(
        self,
        config: Config,
        client: MCPClient,
        tool_info: MCPServerInfo,
        name: str,
    ) -> None:
        super().__init__(config)
        self._tool_info = tool_info
        self._client = client
        self.name = name
        self.description = self._build_description()
        self._validator = MCPArgumentValidator(tool_info.input_schema or {})

    # ── Description visible to the LLM ───────────────────────────────────────

    def _build_description(self) -> str:
        """
        Combine the server-provided description with a compact schema summary
        so the LLM always has field names, types, and requirements inline.
        This dramatically reduces hallucinated argument shapes.
        """
        base = self._tool_info.description or ""
        schema = self._tool_info.input_schema or {}
        props = schema.get("properties", {})
        req = set(schema.get("required", []))

        if not props:
            return base

        lines: list[str] = [base, "", "Parameters:"]
        for field_name, prop in props.items():
            req_marker = "(required)" if field_name in req else "(optional)"
            type_str = prop.get("type", "any")
            desc = prop.get("description", "")
            enum_values = prop.get("enum")
            default = prop.get("default")

            line = f"  - {field_name} {req_marker}: {type_str}"
            if enum_values is not None:
                line += f", must be one of: {enum_values}"
            if default is not None:
                line += f", default: {default!r}"
            if desc:
                line += f"\n      {desc}"
            lines.append(line)

        lines.append("")
        lines.append(
            "IMPORTANT: Send arguments exactly as typed above. "
            "Do not wrap values in extra quotes. "
            "Do not omit required fields. "
            "Do not invent field names that are not listed."
        )

        return "\n".join(lines)

    # ── Schema forwarded to the LLM ──────────────────────────────────────────

    @property
    def schema(self) -> dict[str, Any]:
        """
        Forward the full inputSchema verbatim.
        The previous implementation stripped property descriptions, enums,
        patterns, and examples — which is exactly why the LLM hallucinated.
        We add `type: object` and `additionalProperties: false` if missing
        to give the LLM a tighter contract.
        """
        raw = self._tool_info.input_schema or {}
        return {
            "type":                 raw.get("type", "object"),
            "properties":           raw.get("properties", {}),
            "required":             raw.get("required", []),
            "additionalProperties": raw.get("additionalProperties", False),
            # Preserve anything else the server sent (examples, $defs, etc.)
            **{k: v for k, v in raw.items()
               if k not in ("type", "properties", "required", "additionalProperties")},
        }

    def is_mutating(self, params: Any) -> bool:
        return True

    kind = ToolKind.MCP

    # ── Execute ───────────────────────────────────────────────────────────────

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        # 1. Validate and coerce before touching the network
        coerced_args, errors = self._validator.validate_and_coerce(
            invocation.params, self._tool_info.name
        )
        if errors:
            error_body = (
                f"Tool '{self._tool_info.name}' was called with invalid arguments.\n\n"
                + "\n".join(f"• {e}" for e in errors)
                + "\n\nPlease fix the arguments and call the tool again."
            )
            return ToolResult.error_result(error_body)

        # 2. Call the MCP server with validated, coerced arguments
        try:
            result = await self._client.call_tool(self._tool_info.name, coerced_args)
            output = result.get("output", "")
            is_error = result.get("is_error", False)

            if is_error:
                # Wrap server-side errors with tool context so the LLM knows
                # which tool failed and can retry with corrected arguments.
                return ToolResult.error_result(
                    f"Tool '{self._tool_info.name}' returned an error:\n{output}"
                )

            return ToolResult.success_result(output)

        except RuntimeError as e:
            # Connection-level errors (disconnected, timeout)
            return ToolResult.error_result(
                f"MCP server '{self._client.name}' is unavailable: {e}\n"
                "The server may have disconnected. Try again or check server status."
            )
        except Exception as e:
            return ToolResult.error_result(
                f"Unexpected error calling '{self._tool_info.name}': {e}"
            )
