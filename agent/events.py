from enum import Enum
from dataclasses import dataclass, field
from typing import Any


class AgentEventType(str, Enum):
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_ERROR = "agent_error"

    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"


@dataclass
class AgentEvent:
    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)
