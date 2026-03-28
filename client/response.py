# to wait till the entire file is loaded, and wait for the tokenusage class to be initialized
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any


@dataclass
class TextDelta:
    # the next chunk the llm will provide
    content: str

    def __str__(self) -> str:
        return self.content

# Streameventtype is a child class of str and enum, () with classes is used for inheritance


class StreamEventType(str, Enum):  # str pehle hai to .value nai likhna padega
    TEXT_DELTA = "text_delta"
    MESSAGE_COMPLETE = "message_complete"
    ERROR = "error"

    # tool call
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_COMPLETE = "tool_call_complete"


@dataclass
class TokenUsage:
    prompt_tokens: int = 0  # input tokens, always increase on increase in context
    completion_tokens: int = 0  # output tokens, vary according to the output, large if tool calls are used
    total_tokens: int = 0  # prompt+completion
    cached_tokens: int = 0

    def __add__(self, other: TokenUsage):
        return TokenUsage(
            prompt_tokens=self.prompt_tokens+other.prompt_tokens,
            completion_tokens=self.completion_tokens+other.completion_tokens,
            total_tokens=self.total_tokens+other.total_tokens,
            cached_tokens=self.cached_tokens+other.cached_tokens
        )


@dataclass
class ToolCallDelta:
    call_id: str
    name: str | None = None
    arguments_delta: str = ""


@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamEvent:
    type: StreamEventType
    text_delta: TextDelta | None = None
    tool_call_delta: ToolCallDelta | None = None
    tool_call: ToolCall | None = None
    error: str | None = None
    finish_reason: str | None = None
    usage: TokenUsage | None = None


@dataclass
class ToolResultMessage:
    tool_call_id: str
    content: str
    is_error: bool = False

    def to_openai_message(self) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.content,
        }


def parse_tool_call_arguments(arguments_str: str) -> dict[str, Any]:
    if not arguments_str:
        return {}
    try:
        return json.loads(arguments_str)
    except json.JSONDecodeError:
        return {"raw_arguments": arguments_str}
