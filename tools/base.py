from __future__ import annotations
import abc  # to create an abstract base class in python
from enum import Enum
from typing import Any
from pydantic import BaseModel, ValidationError
from dataclasses import dataclass, field
from pathlib import Path
from pydantic.json_schema import model_json_schema
import difflib


class ToolKind(str, Enum):
    READ = "read"
    WRITE = "write"
    SHELL = "shell"
    NETWORK = "network"
    MEMORY = "memory"
    MCP = "mcp"


@dataclass
class FileDiff:
    path: Path
    old_content: str
    new_content: str

    is_new_file: bool = False
    is_deletion: bool = False

    def create_diff(self) -> str:
        old_lines = self.old_content.splitlines(keepends=True)
        new_lines = self.new_content.splitlines(keepends=True)

        if old_lines and not old_lines[-1].endswith('\n'):
            old_lines[-1] += '\n'
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] += '\n'

        old_name = '/dev/null' if self.is_new_file else str(self.path)
        new_name = '/dev/null' if self.is_deletion else str(self.path)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_name,
            tofile=new_name
        )

        return "".join(diff)


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
    # used to provide structured feedback to the LLM and better UI to the user
    # invoke() method returns a toolresult,
    # result = await self.session.tool_registry.invoke(...)
    # yield AgentEvent.tool_call_complete(
    #     tool_call.call_id,
    #     tool_call.name,
    #     result
    # )
    # elif event.type == AgentEventType.TOOL_CALL_COMPLETE: render something in the UI

    # tool_call_results.append(
    #     ToolResultMessage(
    #         tool_call_id=tool_call.call_id,
    #         content=result.to_model_output(),
    #         is_error=not result.success
    #     )
    # )

    #     self.session.context_manager.add_tool_result(
    #     tool_result.tool_call_id,
    #     tool_result.content
    # )
    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # field is only used for dataclasses, not for random objects, outside dataclass used {} only to initialize dicts

    truncated: bool = False
    diff: FileDiff | None = None

    @classmethod
    def error_result(cls, error: str, output: str = "", **kwargs: Any):
        return cls(success=False,
                   output=output,
                   error=error,
                   **kwargs)

    @classmethod
    def success_result(cls, output: str = "", **kwargs: Any):
        return cls(success=True,
                   output=output,
                   error=None,
                   **kwargs)
    # this cant be a classmethod, we are using this in an instance so, no cls, no classmethod

    def to_model_output(self) -> str:  # type: ignore
        # self is needed here because result= toolresult()
        # and result is a instance here, and not a class member
        # instances need to be accessed using self only, and not cls
        if self.success:
            return self.output

        return f"Error: {self.error}\n\nOutput:\n{self.output}"


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

    # converting the pydantic schema to a dict so that it can be easily passed into kwargs in llmclient.py
    def to_openai_schema(self) -> dict[str, Any]:
        schema = self.schema

        if isinstance(schema, type) and issubclass(schema, BaseModel):
            # now converting the schema to an actual class instance here
            json_schema = model_json_schema(schema, mode="serialization")

            return {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    # eg of properties -> location, city,state
                    "properties": json_schema.get("properties", []),
                    # location of city is required to ge the weather
                    "required": json_schema.get("required", [])
                }
            }

        if isinstance(schema, dict):
            return {
                "name": self.name,
                "description": self.description,
                "parameters": schema.get("parameters", schema)
            }

        raise ValueError(f"invalid schema type for tool {self.name} : {type(schema)} ")
