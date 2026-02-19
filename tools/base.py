from __future__ import annotations
import abc  # to create an abstract class in python
from enum import Enum
from typing import Any
from pydantic import BaseModel, ValidationError
from dataclasses import dataclass, field
from pathlib import Path


class ToolKind(str, Enum):
    READ = "read"
    WRITE = "write"
    SHELL = "shell"
    NETWORK = "network"
    MEMORY = "memory"
    MCP = "mcp"


@dataclass
class ToolInvocation:
    cwd: Path
    params: dict[str, Any]


@dataclass
class ToolConfirmation:
    tool_name: str
    params: dict[str, Any]
    description: str


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(abc.ABC):
    name: str = "base_tool"
    description: str = "Base tool"
    kind: ToolKind = ToolKind.READ

    def __init__(self) -> None:
        pass

    @property  # we will only call tool.schema and not tool.schema()
    # method behaves like a property
    def schema(self) -> dict[str, Any] | type['BaseModel']:
        raise NotImplementedError("Tool must define schema property or class attribute")

    @abc.abstractmethod
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        pass

    # to return validation errors in the form of list, else an empty list
    def validate_params(self, params: dict[str, Any]) -> list[str]:
        schema = self.schema
        # for pydantic
        # schema should be of type "type" only, it is not an instance, its just a blueprint, subclass is used to check whether A is a derived class from B or not in (A,B)
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                schema(**params)
                # validationerror is handled by pydantic
            except ValidationError as e:
                errors = []
                for error in e.errors():
                    # to get the error according to the loc key, [] is the default value

                    # {user {profile {age}}} nested is converted into user.profile.age
                    field = ".".join(str(x) for x in error.get("loc", []))
                    # we get the auto error message from pydantic and just append the filed "user.profile.age" is not an integer in the errors list
                    msg = error.get("msg", "Validation Error")
                    errors.append(f"Parameter: '{field}': {msg}")

                return errors
            except Exception as e:
                return [str(e)]

        return []

    def is_mutating(self, params: dict[str, Any]) -> bool:
        return self.kind in (ToolKind.WRITE,
                             ToolKind.SHELL,
                             ToolKind.NETWORK,
                             ToolKind.MEMORY)

    async def get_confirmation(self, invocation: ToolInvocation) -> ToolConfirmation | None:
        # read ops ke liye kya hi user permission lena
        if not self.is_mutating(invocation.params):
            return None

        # tool yeh yeh karne vaala hai, is the user ok or not, returned in a structured package of information
        return ToolConfirmation(tool_name=self.name,
                                params=invocation.params,
                                description=f"Execute {self.name}")
