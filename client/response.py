# to wait till the entire file is loaded, and wait for the tokenusage class to be initialized
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


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


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

    def __add__(self, other: TokenUsage):
        return TokenUsage(
            prompt_tokens=self.prompt_tokens+other.prompt_tokens,
            completion_tokens=self.completion_tokens+other.completion_tokens,
            total_tokens=self.total_tokens+other.total_tokens,
            cached_tokens=self.cached_tokens+other.cached_tokens
        )


@dataclass
class StreamEvent:
    type: StreamEventType
    text_delta: TextDelta | None = None
    error: str | None = None
    finish_reason: str | None = None
    usage: TokenUsage | None = None
